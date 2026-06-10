"""Tests for GDT e-invoice verification service."""

import pytest

from app.services.einvoice import GDTInvoiceVerificationService


class DummyResponse:
    def __init__(self, status_code: int, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_verify_invoice_returns_not_configured_when_missing_credentials(monkeypatch):
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_username", "", raising=False)
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_password", "", raising=False)

    service = GDTInvoiceVerificationService()
    result = await service.verify_invoice("AA/23E", "000001")

    assert result["verified"] is False
    assert result["status"] == "not_configured"


@pytest.mark.asyncio
async def test_verify_invoice_hits_api_and_marks_not_verified(monkeypatch):
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_username", "demo", raising=False)
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_password", "secret", raising=False)
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_base_url", "https://example.test", raising=False)

    service = GDTInvoiceVerificationService()

    async def _fake_get_bearer_token(self, force_refresh: bool = False):
        return "mock-token"

    async def _fake_post_with_bearer(self, client, url, token, json_payload):
        assert token == "mock-token"
        assert url == "https://example.test/query/invoices"
        assert json_payload == {
            "khhdon": "AA/23E",
            "shdon": "000001",
            "mst": "1234567890",
        }
        return DummyResponse(200, {"status": "not_found", "message": "Invoice does not exist"})

    monkeypatch.setattr(GDTInvoiceVerificationService, "_get_bearer_token", _fake_get_bearer_token)
    monkeypatch.setattr(GDTInvoiceVerificationService, "_post_with_bearer", _fake_post_with_bearer)

    result = await service.verify_invoice("AA/23E", "000001", tax_code="1234567890")

    assert result["verified"] is False
    assert result["status_code"] == 200
    assert result["gdt_message"] == "Invoice does not exist"


@pytest.mark.asyncio
async def test_verify_invoice_infers_verification_from_data_block(monkeypatch):
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_username", "demo", raising=False)
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_password", "secret", raising=False)
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_base_url", "https://example.test", raising=False)

    service = GDTInvoiceVerificationService()

    async def _fake_get_bearer_token(self, force_refresh: bool = False):
        return "mock-token"

    async def _fake_post_with_bearer(self, client, url, token, json_payload):
        return DummyResponse(200, {"data": [{"id": "inv-1"}]})

    monkeypatch.setattr(GDTInvoiceVerificationService, "_get_bearer_token", _fake_get_bearer_token)
    monkeypatch.setattr(GDTInvoiceVerificationService, "_post_with_bearer", _fake_post_with_bearer)

    result = await service.verify_invoice("AA/23E", "000001", tax_code="1234567890")

    assert result["verified"] is True
    assert result["status"] == "verified"
    assert result["raw"]["data"][0]["id"] == "inv-1"


def test_coerce_bool_parses_string_booleans():
    service = GDTInvoiceVerificationService()
    assert service._coerce_bool("true") is True
    assert service._coerce_bool("0") is False
    assert service._coerce_bool(1) is True
    assert service._coerce_bool(0) is False
    assert service._coerce_bool(True) is True
    assert service._coerce_bool(False) is False


@pytest.mark.asyncio
async def test_missing_invoice_series_number_short_circuit(monkeypatch):
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_username", "demo", raising=False)
    monkeypatch.setattr("app.services.einvoice.settings.gdt_api_password", "secret", raising=False)

    service = GDTInvoiceVerificationService()
    result = await service.verify_invoice(None, None)

    assert result["status"] == "missing_fields"
    assert result["verified"] is False
