"""
Extraction Service — uses Claude to extract structured fields from raw OCR text.

This is the core intelligence layer. Claude reliably handles:
- Messy OCR output with Vietnamese diacritics
- Multiple invoice formats (printed, handwritten, digital)
- Ambiguous field placement across different templates
"""

import json
import logging
import re
import unicodedata
from typing import Any

try:
    import anthropic
except ImportError:  # local MVP mode can run without Anthropic SDK installed
    anthropic = None

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


EXTRACTION_SYSTEM_PROMPT = """You are an expert Vietnamese accounting assistant specializing in invoice data extraction.

You will receive raw OCR text from a Vietnamese invoice (hóa đơn) and must extract structured data.

Vietnamese invoice fields to extract:
- invoice_series: Ký hiệu hóa đơn (e.g. "AA/23E", "C22TAA")
- invoice_number: Số hóa đơn (numeric, e.g. "0000123")
- invoice_date: Ngày hóa đơn (ISO format YYYY-MM-DD)
- invoice_type: "invoice_vat" (hóa đơn GTGT) | "invoice_sale" (hóa đơn bán hàng) | "receipt" | "other"
- seller_name: Tên đơn vị bán hàng
- seller_tax_code: Mã số thuế người bán (10 or 13 digits)
- seller_address: Địa chỉ người bán
- buyer_name: Tên đơn vị mua hàng
- buyer_tax_code: Mã số thuế người mua (may be null for retail)
- buyer_address: Địa chỉ người mua
- subtotal_amount: Cộng tiền hàng (integer VND, no decimals)
- vat_rate: "0" | "5" | "8" | "10" | "exempt" | "na"
- vat_amount: Tiền thuế GTGT (integer VND)
- total_amount: Tổng tiền thanh toán (integer VND)
- line_items: Array of {name, unit, quantity, unit_price, amount}
- einvoice_code: Mã của cơ quan thuế (if present, 22-character code)
- notes: Any additional notes

Common layouts you should recognize:
1. VNPT e-invoice:
   - Often contains "HÓA ĐƠN GIÁ TRỊ GIA TĂNG", "Mã của cơ quan thuế", "Ký hiệu", "Số", "Ngày ... tháng ... năm ..."
   - Seller block usually appears before buyer block.
2. VIETTEL e-invoice:
   - Often contains "Viettel", "Mẫu số", "Ký hiệu", "Số hóa đơn", "Mã tra cứu"
   - Invoice series may appear near mẫu số / ký hiệu rows.
3. MISA meInvoice:
   - Often contains "meInvoice", "Mã tra cứu", "Ký hiệu", "Số", "Đơn vị bán hàng", "Đơn vị mua hàng"
   - Tax authority code and invoice lookup code may appear near the header.

Rules:
- All VND amounts must be integers (remove dots used as thousand separators)
- Vietnamese thousand separator is "." (period), decimal separator is "," (comma)
- Example: "1.500.000" = 1500000 VND, "1.500.000,50" = 1500000 VND (round down)
- If a field is not found, return null
- Prefer exact invoice identity fields over guessed ones
- Return ONLY valid JSON, no explanation text

Return this exact JSON structure:
{
  "invoice_series": string | null,
  "invoice_number": string | null,
  "invoice_date": string | null,
  "invoice_type": string,
  "seller_name": string | null,
  "seller_tax_code": string | null,
  "seller_address": string | null,
  "buyer_name": string | null,
  "buyer_tax_code": string | null,
  "buyer_address": string | null,
  "subtotal_amount": integer | null,
  "vat_rate": string,
  "vat_amount": integer | null,
  "total_amount": integer | null,
  "line_items": array,
  "einvoice_code": string | null,
  "notes": string | null,
  "confidence": float
}"""


LOW_CONFIDENCE_THRESHOLD = 0.78


class ExtractionService:
    """
    Uses Claude to extract structured fields from raw OCR text.

    Advantages over regex/rule-based extraction:
    - Handles varied invoice templates without hardcoding
    - Robust to OCR errors and unusual formatting
    - Understands Vietnamese accounting context
    """

    def __init__(self):
        self.client = None
        if anthropic and settings.anthropic_api_key and not settings.anthropic_api_key.startswith("your-"):
            self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    async def extract_invoice_fields(
        self,
        ocr_text: str,
        doc_type_hint: str | None = None,
        ocr_confidence: float | None = None,
    ) -> dict[str, Any]:
        """
        Extract structured invoice fields from raw OCR text.

        Returns:
            Dict with extracted fields and confidence score
        """
        regex_result = self._regex_extract(ocr_text)
        if self.client is None:
            return regex_result

        context = []
        if ocr_confidence is not None:
            context.append(f"OCR confidence: {ocr_confidence:.2f}")
        if doc_type_hint:
            context.append(f"Document type hint: {doc_type_hint}")

        user_message = "Extract invoice data from this OCR text."
        if context:
            user_message += "\n" + "\n".join(context)
        user_message += f"\n\n{ocr_text}"

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            extracted = self._validate_and_clean(json.loads(raw))
            return self._merge_with_regex_fallback(extracted, regex_result, ocr_confidence)

        except json.JSONDecodeError as exc:
            logger.error("Claude returned invalid JSON: %s", exc)
            return regex_result
        except Exception as exc:
            logger.error("Extraction failed: %s", exc)
            return regex_result

    def _merge_with_regex_fallback(
        self,
        extracted: dict[str, Any],
        regex_result: dict[str, Any],
        ocr_confidence: float | None,
    ) -> dict[str, Any]:
        merged = dict(extracted)
        extraction_confidence = float(merged.get("confidence") or 0)
        low_confidence = extraction_confidence < LOW_CONFIDENCE_THRESHOLD or (
            ocr_confidence is not None and float(ocr_confidence) < 0.7
        )

        critical_fields = (
            "invoice_series",
            "invoice_number",
            "invoice_date",
            "seller_tax_code",
            "subtotal_amount",
            "vat_amount",
            "total_amount",
            "vat_rate",
            "einvoice_code",
        )

        for field in critical_fields:
            if low_confidence or not merged.get(field):
                fallback = regex_result.get(field)
                if fallback not in (None, "", [], {}):
                    merged[field] = fallback

        if not merged.get("seller_name") and regex_result.get("seller_name"):
            merged["seller_name"] = regex_result["seller_name"]
        if not merged.get("buyer_name") and regex_result.get("buyer_name"):
            merged["buyer_name"] = regex_result["buyer_name"]
        if not merged.get("line_items") and regex_result.get("line_items"):
            merged["line_items"] = regex_result["line_items"]

        if low_confidence and regex_result.get("confidence"):
            merged["confidence"] = max(extraction_confidence, float(regex_result["confidence"]) - 0.05)
            merged["notes"] = self._append_note(
                merged.get("notes"),
                "Fields partially recovered with deterministic fallback due to low OCR/model confidence.",
            )
        return self._validate_and_clean(merged)

    def _validate_and_clean(self, data: dict[str, Any]) -> dict[str, Any]:
        for field in ("subtotal_amount", "vat_amount", "total_amount"):
            if val := data.get(field):
                try:
                    cleaned = self._normalize_amount_string(str(val))
                    data[field] = int(cleaned) if cleaned is not None else None
                except (ValueError, TypeError):
                    data[field] = None

        for field in ("seller_tax_code", "buyer_tax_code"):
            if val := data.get(field):
                digits_only = "".join(c for c in str(val) if c.isdigit())
                data[field] = digits_only if digits_only else None

        valid_vat_rates = {"0", "5", "8", "10", "exempt", "na"}
        if data.get("vat_rate") not in valid_vat_rates:
            data["vat_rate"] = "10"

        if not isinstance(data.get("line_items"), list):
            data["line_items"] = []

        confidence = data.get("confidence", 0.5)
        data["confidence"] = max(0.0, min(1.0, float(confidence)))

        return data

    def _empty_result(self) -> dict[str, Any]:
        return {
            "invoice_series": None,
            "invoice_number": None,
            "invoice_date": None,
            "invoice_type": "other",
            "seller_name": None,
            "seller_tax_code": None,
            "seller_address": None,
            "buyer_name": None,
            "buyer_tax_code": None,
            "buyer_address": None,
            "subtotal_amount": None,
            "vat_rate": "10",
            "vat_amount": None,
            "total_amount": None,
            "line_items": [],
            "einvoice_code": None,
            "notes": None,
            "confidence": 0.0,
        }

    def _regex_extract(self, text: str) -> dict[str, Any]:
        normalized = self._normalize_text(text)

        tax_codes = re.findall(r"(?:ma so thue|mst)\s*:?\s*([0-9\-\s]{10,16})", normalized, flags=re.IGNORECASE)
        invoice_date = self._extract_invoice_date(normalized)
        invoice_series = self._find_first(
            normalized,
            [
                r"ky hieu(?: hoa don)?\s*:?\s*([A-Z0-9\/\-]{4,20})",
                r"mau so\s*[0-9a-z\/\-]*\s+ky hieu\s*:?\s*([A-Z0-9\/\-]{4,20})",
            ],
        )
        invoice_number = self._find_first(
            normalized,
            [
                r"so(?: hoa don)?\s*:?\s*([0-9]{3,12})",
            ],
        )
        subtotal_amount = self._extract_amount(normalized, ["cong tien hang", "thanh tien"])
        vat_amount = self._extract_amount(normalized, ["tien thue gtgt", "thue gtgt"])
        total_amount = self._extract_amount(normalized, ["tong cong tien thanh toan", "tong tien thanh toan"])
        vat_rate = self._extract_vat_rate(normalized)

        seller_name = self._find_first(
            normalized,
            [
                r"(?:don vi ban hang|nguoi ban|ten don vi ban)\s*:?\s*(.+)",
            ],
        )
        buyer_name = self._find_first(
            normalized,
            [
                r"(?:don vi mua hang|nguoi mua|ten don vi mua)\s*:?\s*(.+)",
            ],
        )
        seller_address = self._find_first(
            normalized,
            [
                r"dia chi\s*:?\s*(.+)",
            ],
        )
        item_name = self._find_first(
            normalized,
            [
                r"(?:hang hoa dich vu|ten hang hoa, dich vu|dien giai)\s*:?\s*(.+)",
            ],
        )
        einvoice_code = self._find_first(
            normalized,
            [
                r"(?:ma cua co quan thue|ma cqt)\s*:?\s*([A-Z0-9]{8,30})",
            ],
        )

        inferred_type = "invoice_vat" if "hoa don gia tri gia tang" in normalized or "thue gtgt" in normalized else "invoice_sale"

        data = {
            "invoice_series": invoice_series,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "invoice_type": inferred_type,
            "seller_name": seller_name,
            "seller_tax_code": tax_codes[0] if len(tax_codes) > 0 else None,
            "seller_address": seller_address,
            "buyer_name": buyer_name,
            "buyer_tax_code": tax_codes[1] if len(tax_codes) > 1 else None,
            "buyer_address": None,
            "subtotal_amount": subtotal_amount,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "total_amount": total_amount,
            "line_items": [{
                "name": item_name or "Uploaded accounting document",
                "unit": None,
                "quantity": 1,
                "unit_price": subtotal_amount,
                "amount": subtotal_amount or 0,
            }],
            "einvoice_code": einvoice_code,
            "notes": "Extracted with deterministic fallback.",
            "confidence": self._score_regex_result(
                invoice_series=invoice_series,
                invoice_number=invoice_number,
                seller_tax_code=data_tax(tax_codes, 0),
                total_amount=total_amount,
                invoice_date=invoice_date,
            ),
        }
        return self._validate_and_clean(data)

    def _extract_invoice_date(self, text: str) -> str | None:
        spelled = re.search(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})", text, flags=re.IGNORECASE)
        if spelled:
            day, month, year = spelled.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"

        numeric = re.search(r"(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})", text)
        if numeric:
            day, month, year = numeric.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        return None

    def _extract_amount(self, text: str, labels: list[str]) -> int | None:
        for label in labels:
            match = re.search(rf"{label}\s*:?\s*([\d\.,]+)", text, flags=re.IGNORECASE)
            if match:
                normalized = self._normalize_amount_string(match.group(1))
                if normalized is not None:
                    return int(normalized)
        return None

    def _extract_vat_rate(self, text: str) -> str:
        match = re.search(r"(?:thue suat gtgt|vat)\s*:?\s*(0|5|8|10)\s*%", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        if "khong chiu thue" in text:
            return "exempt"
        return "10"

    def _find_first(self, text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = value.split("\n")[0].strip()
                return value if value else None
        return None

    def _normalize_text(self, text: str) -> str:
        folded = unicodedata.normalize("NFKD", text)
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        folded = folded.replace("Đ", "D").replace("đ", "d")
        return folded

    def _normalize_amount_string(self, value: str) -> int | None:
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else None

    def _score_regex_result(
        self,
        *,
        invoice_series: str | None,
        invoice_number: str | None,
        seller_tax_code: str | None,
        total_amount: int | None,
        invoice_date: str | None,
    ) -> float:
        score = 0.4
        if invoice_series:
            score += 0.12
        if invoice_number:
            score += 0.12
        if seller_tax_code:
            score += 0.12
        if total_amount:
            score += 0.12
        if invoice_date:
            score += 0.12
        return min(score, 0.9)

    def _append_note(self, existing: str | None, note: str) -> str:
        if not existing:
            return note
        if note in existing:
            return existing
        return f"{existing}\n{note}"


def data_tax(values: list[str], index: int) -> str | None:
    return values[index] if len(values) > index else None
