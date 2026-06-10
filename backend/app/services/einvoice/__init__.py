"""GDT e-Invoice verification integration."""

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GDTInvoiceVerificationService:
    """
    Verify invoices against the General Department of Taxation (GDT) portal.

    Expected lookup body (as documented in project notes):
      {"khhdon": "...", "shdon": "...", "mst": "..."}
    """

    # API paths are intentionally configurable by changing this module only.
    QUERY_PATH = "/query/invoices"
    AUTH_PATHS = ("/api/auth/login", "/oauth/token", "/auth/login")

    def __init__(self):
        self.base_url = settings.gdt_api_base_url.rstrip("/")
        self.username = settings.gdt_api_username
        self.password = settings.gdt_api_password
        self.company_tax_code = settings.gdt_tax_code
        self._bearer_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def verify_invoice(
        self,
        invoice_series: str | None,
        invoice_number: str | None,
        tax_code: str | None = None,
    ) -> dict[str, Any]:
        """
        Return verification result from GDT.

        response schema (normalized):
          {
            "verified": bool,
            "status": "verified" | "not_verified" | "not_configured" | ...,
            "invoice_series": str|None,
            "invoice_number": str|None,
            "tax_code": str|None,
            "status_code": int|None,
            "gdt_message": str|None,
            "raw": dict|list|None
          }
        """
        if not self._has_credentials():
            return {
                "verified": False,
                "status": "not_configured",
                "invoice_series": invoice_series,
                "invoice_number": invoice_number,
                "tax_code": tax_code or self.company_tax_code,
                "status_code": None,
                "gdt_message": "GDT credentials are not configured",
                "raw": None,
            }

        if not invoice_series or not invoice_number:
            return {
                "verified": False,
                "status": "missing_fields",
                "invoice_series": invoice_series,
                "invoice_number": invoice_number,
                "tax_code": tax_code or self.company_tax_code,
                "status_code": None,
                "gdt_message": "Missing invoice series/number",
                "raw": None,
            }

        try:
            token = await self._get_bearer_token()
        except Exception as exc:  # pragma: no cover - defensive for API availability
            return {
                "verified": False,
                "status": "auth_failed",
                "invoice_series": invoice_series,
                "invoice_number": invoice_number,
                "tax_code": tax_code or self.company_tax_code,
                "status_code": None,
                "gdt_message": str(exc),
                "raw": None,
            }

        payload = {
            "khhdon": invoice_series,
            "shdon": invoice_number,
            "mst": (tax_code or self.company_tax_code or "").strip(),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await self._post_with_bearer(
                client,
                f"{self.base_url}{self.QUERY_PATH}",
                token=token,
                json_payload=payload,
            )
            status_code = response.status_code

            if status_code == 401:
                # Token may be expired or revoked unexpectedly; retry once with fresh token.
                self._bearer_token = None
                self._token_expires_at = None
                token = await self._get_bearer_token(force_refresh=True)
                response = await self._post_with_bearer(
                    client,
                    f"{self.base_url}{self.QUERY_PATH}",
                    token=token,
                    json_payload=payload,
                )
                status_code = response.status_code

            raw = self._parse_json(response)
            verified, message = self._infer_verification_status(raw, status_code)

            return {
                "verified": verified,
                "status": "verified" if verified else "not_verified",
                "invoice_series": invoice_series,
                "invoice_number": invoice_number,
                "tax_code": payload["mst"] or None,
                "status_code": status_code,
                "gdt_message": message,
                "raw": raw,
            }

    async def _get_bearer_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._bearer_token and self._token_expires_at:
            # Expire a little early to avoid clock-skew edge.
            if datetime.utcnow() < (self._token_expires_at - timedelta(minutes=2)):
                return self._bearer_token

        for auth_path in self.AUTH_PATHS:
            try:
                token = await self._login(auth_path=auth_path)
            except Exception as exc:
                logger.warning("GDT auth attempt failed on %s: %s", auth_path, exc)
                continue
            if token:
                return token

        raise RuntimeError("Failed to authenticate with GDT using available auth endpoints.")

    async def _login(self, auth_path: str) -> str:
        login_url = f"{self.base_url}{auth_path}"
        payloads = [
            {"username": self.username, "password": self.password},
            {"userName": self.username, "passWord": self.password},
            {"account": self.username, "secret": self.password},
        ]

        async with httpx.AsyncClient(timeout=20.0) as client:
            last_exc: Exception | None = None
            for payload in payloads:
                response = await client.post(login_url, json=payload)
                if response.status_code < 200 or response.status_code >= 300:
                    last_exc = RuntimeError(
                        f"Auth endpoint returned {response.status_code}: {response.text[:200]}"
                    )
                    continue
                data = self._parse_json(response) or {}
                token = self._extract_token(data)
                if not token:
                    # Try nested body structure if returned.
                    token = self._extract_token(data.get("data", {})) if isinstance(data, dict) else None
                if token:
                    expires_in = self._extract_expires_in(data)
                    self._bearer_token = token
                    self._token_expires_at = datetime.utcnow() + (
                        timedelta(seconds=expires_in) if expires_in else timedelta(hours=8)
                    )
                    return token
                last_exc = RuntimeError("Auth response did not include access token.")

        if last_exc:
            raise last_exc
        raise RuntimeError(f"GDT auth failed for {login_url}")

    async def _post_with_bearer(
        self,
        client: httpx.AsyncClient,
        url: str,
        token: str,
        json_payload: dict[str, Any],
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = await client.post(url, headers=headers, json=json_payload)
        if response.status_code == 404:
            # Some deployments expose query API under different mount points.
            alt_url = url.replace("/query/invoices", "/api/query/invoices")
            response = await client.post(alt_url, headers=headers, json=json_payload)
        return response

    def _infer_verification_status(self, raw: Any, status_code: int) -> tuple[bool, str]:
        if status_code >= 500:
            return False, f"GDT server error ({status_code})"
        if status_code == 401 or status_code == 403:
            return False, "Unauthorized from GDT"
        if status_code == 404:
            return False, "GDT verification endpoint not found"
        if status_code and status_code >= 400:
            return False, f"GDT returned HTTP {status_code}"
        if not isinstance(raw, dict):
            return False, "Unexpected GDT response format"

        status_value = raw.get("status")
        if status_value is not None:
            normalized = str(status_value).strip().lower()
            if normalized in {"success", "ok", "found", "verified", "1", "true", "y", "yes"}:
                return True, raw.get("message") or "Verified"
            if normalized in {"fail", "failed", "invalid", "not_found", "notfound", "error", "0", "false", "n", "no"}:
                return False, raw.get("message") or "Not verified"

        for key in ("verified", "valid", "is_valid", "isValid", "isverified", "isVerified"):
            if key in raw:
                try:
                    return self._coerce_bool(raw.get(key)), raw.get("message")
                except Exception:
                    pass

        data = raw.get("data")
        if isinstance(data, list):
            return (len(data) > 0, raw.get("message") or "Matched invoice records")
        if isinstance(data, dict):
            if data:
                return True, raw.get("message") or "Matched invoice data"
            return False, raw.get("message") or "No invoice data returned"

        return False, raw.get("message") or "Unable to infer verification status"

    def _coerce_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y"}:
                return True
            if normalized in {"0", "false", "no", "n"}:
                return False
        return bool(value)

    def _extract_token(self, data: dict[str, Any]) -> str | None:
        for key in ("access_token", "token", "jwt", "id_token", "bearer", "auth"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_expires_in(self, data: dict[str, Any]) -> int | None:
        for key in ("expires_in", "expiresIn", "exp"):
            value = data.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    def _parse_json(self, response: httpx.Response) -> Any | None:
        try:
            return response.json()
        except Exception:
            return {"error": response.text[:400]}

    def _has_credentials(self) -> bool:
        return bool(self.username and self.password and not str(self.username).startswith("your-") and not str(self.password).startswith("your-"))
