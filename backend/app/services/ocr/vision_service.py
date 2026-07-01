"""
PaddleOCR and Mock OCR providers.

These are used when OCR_ENGINE is set to 'paddle' (offline fallback)
or 'mock' (development / testing).

Production default is OCR_ENGINE=google (see google_vision.py).
"""

import asyncio
import base64
import io
import logging
import tempfile
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

# Re-export shared types so existing imports from this module still work
from app.services.ocr.providers import OCRResult, OCRProviderError, OCRPage

# Lazy import for PaddleOCR (heavy dependency)
_paddleocr = None


def _get_paddleocr():
    global _paddleocr
    if _paddleocr is None:
        try:
            from paddleocr import PaddleOCR

            _paddleocr = PaddleOCR
        except ImportError:
            return None
    return _paddleocr


# ---------------------------------------------------------------------------
# Mock OCR Provider
# ---------------------------------------------------------------------------

_MOCK_INVOICE_TEXT = """
HOA DON GIA TRI GIA TANG
Ky hieu: 1C26TAA
So: 0000123
Ngay 02 thang 06 nam 2026
Don vi ban hang: CONG TY TNHH NHA CUNG CAP DEMO
Ma so thue: 0312345678
Dia chi: 12 Nguyen Hue, Quan 1, TP Ho Chi Minh
Don vi mua hang: Cong ty TNHH Demo Viet Nam
Ma so thue: 0101243150
Dia chi: Quan 1, TP Ho Chi Minh
Hang hoa dich vu: Dich vu tu van ke toan
Thanh tien: 5.000.000
Thue suat GTGT: 10%
Tien thue GTGT: 500.000
Tong cong tien thanh toan: 5.500.000
Ma cua co quan thue: CQTDEMO123456789
"""


class MockOCRProvider:
    """
    Deterministic mock OCR for development and testing.

    Always returns the same well-formed mock invoice regardless of input.
    """

    ENGINE_VERSION = "1.0.0-mock"

    def __init__(self, settings: "Settings"):
        self.settings = settings

    async def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> OCRResult:
        """Return a deterministic mock invoice regardless of input."""
        text = _MOCK_INVOICE_TEXT.strip()
        page = OCRPage(page_number=1, text=text, confidence=0.82)
        return OCRResult(
            text=text,
            confidence=0.82,
            provider="mock",
            page_count=1,
            blocks=[],
            warnings=[],
            duration_ms=0.0,
            pages=[page],
        )

    async def extract_text_from_pdf(self, pdf_bytes: bytes) -> OCRResult:
        """Return a single-page mock result for PDFs."""
        text = _MOCK_INVOICE_TEXT.strip()
        page = OCRPage(page_number=1, text=text, confidence=0.82)
        return OCRResult(
            text=text,
            confidence=0.82,
            provider="mock",
            page_count=1,
            blocks=[],
            warnings=[],
            duration_ms=0.0,
            pages=[page],
        )


# ---------------------------------------------------------------------------
# PaddleOCR Provider
# ---------------------------------------------------------------------------

_marker = object()


@dataclass
class _OCRCandidate:
    name: str
    image_bytes: bytes
    mime_type: str


class PaddleOCRProvider:
    """
    PaddleOCR provider — runs locally without internet.

    WARNING: On Apple Silicon (M1/M2/M3) without GPU, PaddleOCR is very slow
    (>90s per page). Use OCR_ENGINE=paddle only as an offline fallback, not
    for production traffic.
    """

    ENGINE_VERSION = "paddlepaddle"

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self._ocr = _marker  # lazy

    @property
    def ocr(self):
        if self._ocr is _marker:
            cls = _get_paddleocr()
            if cls is None:
                raise OCRProviderError(
                    "PaddleOCR is not installed. Run: pip install paddlepaddle paddleocr",
                    provider="paddle",
                )
            self._ocr = cls(
                use_angle_cls=True,
                lang=getattr(self.settings, "paddleocr_lang", "vi"),
                use_gpu=getattr(self.settings, "paddleocr_use_gpu", False),
            )
        return self._ocr

    async def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> OCRResult:
        """Run PaddleOCR with multi-candidate preprocessing and return the best result."""
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._run_candidates, image_bytes, mime_type),
                timeout=getattr(self.settings, "paddleocr_timeout_seconds", 45),
            )
        except asyncio.TimeoutError:
            raise OCRProviderError(
                f"PaddleOCR timed out after {getattr(self.settings, 'paddleocr_timeout_seconds', 45)}s",
                provider="paddle",
            )

        if not result.text.strip():
            logger.warning("PaddleOCR returned empty text; returning empty result")
            return OCRResult(
                text="",
                confidence=0.0,
                provider="paddle",
                duration_ms=(time.monotonic() - start) * 1000,
            )

        result.duration_ms = (time.monotonic() - start) * 1000
        # Add page entry for single-page case
        if not result.pages:
            result.pages.append(OCRPage(page_number=1, text=result.text, confidence=result.confidence))
        return result

    async def extract_text_from_pdf(self, pdf_bytes: bytes) -> OCRResult:
        """Convert PDF pages to images then run PaddleOCR per page."""
        start = time.monotonic()

        try:
            from pdf2image import convert_from_bytes
        except ImportError:  # pragma: no cover
            raise OCRProviderError(
                "pdf2image is required for PDF OCR with PaddleOCR. "
                "Install with: pip install pdf2image",
                provider="paddle",
            )

        try:
            pdf_pages = convert_from_bytes(pdf_bytes, dpi=200, fmt="jpeg", thread_count=2)
        except Exception as exc:
            raise OCRProviderError(f"pdf2image failed: {exc}", provider="paddle") from exc

        all_texts: list[str] = []
        all_confidences: list[float] = []
        total_blocks: list[dict] = []
        ocr_pages: list[OCRPage] = []

        for i, page_img in enumerate(pdf_pages, start=1):
            buf = io.BytesIO()
            if page_img.mode not in ("RGB",):
                page_img = page_img.convert("RGB")
            page_img.save(buf, format="JPEG", quality=85)
            page_bytes = buf.getvalue()

            page_result = await self.extract_text(page_bytes, "image/jpeg")
            all_texts.append(f"[--- Page {i} ---]\n{page_result.text}")
            all_confidences.append(page_result.confidence)
            total_blocks.extend(page_result.blocks)
            ocr_pages.append(OCRPage(page_number=i, text=page_result.text, confidence=page_result.confidence))

        return OCRResult(
            text="\n\n".join(all_texts),
            confidence=sum(all_confidences) / len(all_confidences) if all_confidences else 0.0,
            provider="paddle",
            page_count=len(pdf_pages),
            blocks=total_blocks,
            duration_ms=(time.monotonic() - start) * 1000,
            pages=ocr_pages,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_candidates(self, image_bytes: bytes, mime_type: str) -> OCRResult:
        """Run PaddleOCR on multiple preprocessing candidates and return the best."""
        candidates = self._preprocess_candidates(image_bytes, mime_type)

        best_result = OCRResult(text="", confidence=0.0, provider="paddle")
        best_score = -1.0

        for candidate in candidates:
            result = self._run_single_pass(candidate)
            score = self._score_ocr_result(result)
            if score > best_score:
                best_score = score
                best_result = result

        return best_result

    def _run_single_pass(self, candidate: _OCRCandidate) -> OCRResult:
        suffix = ".png" if candidate.mime_type == "image/png" else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(candidate.image_bytes)
            tmp.flush()
            raw_result = self.ocr.ocr(tmp.name, cls=True)

        lines: list[str] = []
        confidences: list[float] = []
        blocks: list[dict] = []

        for page in raw_result or []:
            for line in page or []:
                if not line or len(line) < 2:
                    continue
                text_conf = line[1]
                if not text_conf or len(text_conf) < 2:
                    continue
                text = str(text_conf[0]).strip()
                confidence = float(text_conf[1] or 0)
                if text:
                    lines.append(text)
                    confidences.append(confidence)
                    blocks.append({
                        "text": text,
                        "confidence": confidence,
                        "bounding_box": line[0],
                    })

        return OCRResult(
            text="\n".join(lines),
            confidence=sum(confidences) / len(confidences) if confidences else 0.0,
            provider="paddle",
            blocks=blocks,
        )

    def _score_ocr_result(self, result: OCRResult) -> float:
        """Score an OCR result to pick the best candidate."""
        text = result.text or ""
        score = float(result.confidence or 0)
        score += min(len(text) / 1500.0, 0.25)
        if "ma so thue" in text.lower() or "mst" in text.lower():
            score += 0.1
        if "tong cong" in text.lower():
            score += 0.05
        if _has_invoice_markers(text):
            score += 0.1
        return score

    def _preprocess_candidates(self, image_bytes: bytes, mime_type: str) -> list[_OCRCandidate]:
        """Generate multiple image preprocessing candidates to improve OCR accuracy."""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            base = self._normalize_image(img)
            thresholded = self._threshold_image(base)
            sharpened = self._sharpen_image(base)

            return [
                _OCRCandidate("normalized", self._to_jpeg(base), "image/jpeg"),
                _OCRCandidate("thresholded", self._to_jpeg(thresholded), "image/jpeg"),
                _OCRCandidate("sharpened", self._to_jpeg(sharpened), "image/jpeg"),
            ]
        except Exception as exc:
            logger.warning("Image preprocessing failed, using original: %s", exc)
            return [_OCRCandidate("original", image_bytes, mime_type)]

    def _normalize_image(self, img: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(img)
        gray = ImageOps.autocontrast(gray, cutoff=2)
        gray = gray.filter(ImageFilter.MedianFilter(size=3))
        gray = ImageEnhance.Contrast(gray).enhance(1.45)

        max_dim = max(gray.size)
        if max_dim < 1600:
            scale = 1600 / max_dim
            new_size = (int(gray.size[0] * scale), int(gray.size[1] * scale))
            gray = gray.resize(new_size, Image.LANCZOS)
        return gray

    def _threshold_image(self, img: Image.Image) -> Image.Image:
        return img.point(lambda px: 255 if px > 168 else 0, mode="1").convert("L")

    def _sharpen_image(self, img: Image.Image) -> Image.Image:
        sharpened = img.filter(ImageFilter.SHARPEN)
        return sharpened.filter(ImageFilter.UnsharpMask(radius=1.8, percent=180, threshold=2))

    def _to_jpeg(self, img: Image.Image) -> bytes:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()


def re_has_invoice_markers(text: str) -> bool:
    """Alias for _has_invoice_markers — kept for backwards compatibility."""
    return _has_invoice_markers(text)


def _has_invoice_markers(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("hoa don", "ky hieu", "tong cong", "ma so thue"))


# ---------------------------------------------------------------------------
# Legacy export — keep for backwards compatibility
# ---------------------------------------------------------------------------

class OCRService:  # pragma: no cover
    """
    Legacy compatibility wrapper.

    New code should use `from app.services.ocr.providers import get_ocr_provider`
    instead of instantiating OCRService directly.
    """

    def __init__(self):
        from app.services.ocr.providers import get_ocr_provider

        self._provider = get_ocr_provider()

    async def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg"):
        return await self._provider.extract_text(image_bytes, mime_type)
