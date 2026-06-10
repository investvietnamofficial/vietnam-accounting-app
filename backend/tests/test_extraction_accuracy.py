from app.services.extraction.claude_extractor import ExtractionService
from app.services.ocr.vision_service import OCRService, re_has_invoice_markers


def test_regex_extract_handles_vietnamese_invoice_fields():
    service = ExtractionService()
    result = service._regex_extract(
        """
        HOA DON GIA TRI GIA TANG
        Ky hieu hoa don: AA/23E
        So hoa don: 0000123
        Ngay 02 thang 06 nam 2026
        Don vi ban hang: CONG TY TNHH VNPT DEMO
        Ma so thue: 0312345678
        Don vi mua hang: CONG TY TNHH KHACH HANG
        Ma so thue: 0101243150
        Cong tien hang: 1.500.000
        Tien thue GTGT: 150.000
        Tong cong tien thanh toan: 1.650.000
        Ma cua co quan thue: CQTABC123456789
        """
    )

    assert result["invoice_series"] == "AA/23E"
    assert result["invoice_number"] == "0000123"
    assert result["seller_tax_code"] == "0312345678"
    assert result["buyer_tax_code"] == "0101243150"
    assert result["subtotal_amount"] == 1500000
    assert result["vat_amount"] == 150000
    assert result["total_amount"] == 1650000


def test_merge_with_regex_fallback_recovers_missing_fields():
    service = ExtractionService()
    regex_result = service._regex_extract(
        """
        Ky hieu: C22TAA
        So: 12345
        Ngay 02 thang 06 nam 2026
        Ma so thue: 0312345678
        Tong cong tien thanh toan: 2.200.000
        """
    )
    model_result = service._validate_and_clean(
        {
            "invoice_series": None,
            "invoice_number": None,
            "invoice_date": None,
            "invoice_type": "invoice_vat",
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
            "confidence": 0.41,
        }
    )

    merged = service._merge_with_regex_fallback(model_result, regex_result, 0.6)
    assert merged["invoice_series"] == "C22TAA"
    assert merged["invoice_number"] == "12345"
    assert merged["seller_tax_code"] == "0312345678"
    assert merged["total_amount"] == 2200000
    assert "deterministic fallback" in (merged["notes"] or "").lower()


def test_ocr_preprocess_candidates_produces_multiple_variants():
    service = OCRService()
    from PIL import Image
    import io

    image = Image.new("RGB", (300, 180), "white")
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    candidates = service._preprocess_candidates(buf.getvalue(), "image/jpeg")

    assert len(candidates) >= 3
    assert all(candidate.image_bytes for candidate in candidates)


def test_invoice_marker_heuristic_detects_invoice_like_text():
    assert re_has_invoice_markers("HOA DON GIA TRI GIA TANG\nMa so thue: 0312345678") is True
