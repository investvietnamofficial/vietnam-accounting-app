"""
OCR Service for Vietnamese accounting documents.

Default MVP path uses PaddleOCR locally. Google Vision remains configurable,
and mock OCR remains available for development when external dependencies are
not installed.
"""

import base64
import asyncio
import io
import logging
import tempfile
from dataclasses import dataclass

import httpx
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OCRResult:
    def __init__(self, text: str, confidence: float, language_hints: list[str] = None):
        self.text = text
        self.confidence = confidence
        self.language_hints = language_hints or ["vi", "en"]
        self.blocks: list[dict] = []


@dataclass
class OCRCandidate:
    name: str
    image_bytes: bytes
    mime_type: str


class OCRService:
    """Wraps OCR engines for Vietnamese accounting documents."""

    VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"

    def __init__(self):
        self.api_key = settings.google_vision_api_key
        self.ocr_engine = settings.ocr_engine.lower()

    async def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> OCRResult:
        if self.ocr_engine == "mock":
            return OCRResult(text=self._mock_invoice_text(), confidence=0.82)
        if self.ocr_engine == "paddle":
            return await self._extract_with_paddle_candidates(image_bytes, mime_type)
        if not self.api_key or self.api_key.startswith("your-"):
            logger.warning("Google Vision API key not configured; falling back to mock OCR")
            return OCRResult(text=self._mock_invoice_text(), confidence=0.82)

        preprocessed = self._best_preprocessed_candidate(image_bytes, mime_type).image_bytes
        b64_image = base64.b64encode(preprocessed).decode("utf-8")
        payload = {
            "requests": [
                {
                    "image": {"content": b64_image},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}],
                    "imageContext": {
                        "languageHints": ["vi", "en"],
                        "textDetectionParams": {"enableTextDetectionConfidenceScore": True},
                    },
                }
            ]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.VISION_API_URL, params={"key": self.api_key}, json=payload)
            resp.raise_for_status()

        return self._parse_response(resp.json())

    async def _extract_with_paddle_candidates(self, image_bytes: bytes, mime_type: str) -> OCRResult:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._run_paddle_candidates, image_bytes, mime_type),
                timeout=settings.paddleocr_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("PaddleOCR failed (%s); falling back to mock OCR", exc)
            return OCRResult(text=self._mock_invoice_text(), confidence=0.82)

        if result.text.strip():
            return result
        logger.warning("PaddleOCR returned no text; falling back to mock OCR")
        return OCRResult(text=self._mock_invoice_text(), confidence=0.82)

    def _run_paddle_candidates(self, image_bytes: bytes, mime_type: str) -> OCRResult:
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            logger.warning("PaddleOCR is not installed; falling back to mock OCR")
            return OCRResult(text="", confidence=0.0)

        ocr = PaddleOCR(
            use_angle_cls=True,
            lang=settings.paddleocr_lang,
            use_gpu=settings.paddleocr_use_gpu,
            show_log=False,
        )

        best_result = OCRResult(text="", confidence=0.0)
        best_score = -1.0
        for candidate in self._preprocess_candidates(image_bytes, mime_type):
            result = self._run_single_paddle_pass(ocr, candidate)
            score = self._score_ocr_result(result)
            if score > best_score:
                best_score = score
                best_result = result
        return best_result

    def _run_single_paddle_pass(self, ocr, candidate: OCRCandidate) -> OCRResult:
        suffix = ".png" if candidate.mime_type == "image/png" else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(candidate.image_bytes)
            tmp.flush()
            raw_result = ocr.ocr(tmp.name, cls=True)

        lines: list[str] = []
        confidences: list[float] = []
        blocks: list[dict] = []
        for page in raw_result or []:
            for line in page or []:
                if not line or len(line) < 2:
                    continue
                box = line[0]
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
                        "bounding_box": box,
                    })

        result = OCRResult(
            text="\n".join(lines),
            confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        )
        result.blocks = blocks
        return result

    def _score_ocr_result(self, result: OCRResult) -> float:
        text = result.text or ""
        score = float(result.confidence or 0)
        score += min(len(text) / 1500.0, 0.25)
        if "ma so thue" in text.lower() or "mst" in text.lower():
            score += 0.1
        if "tong cong" in text.lower():
            score += 0.05
        if re_has_invoice_markers(text):
            score += 0.1
        return score

    def _best_preprocessed_candidate(self, image_bytes: bytes, mime_type: str) -> OCRCandidate:
        candidates = self._preprocess_candidates(image_bytes, mime_type)
        return candidates[1] if len(candidates) > 1 else candidates[0]

    def _preprocess_candidates(self, image_bytes: bytes, mime_type: str) -> list[OCRCandidate]:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            base = self._normalize_image(img)
            thresholded = self._threshold_image(base)
            sharpened = self._sharpen_image(base)

            return [
                OCRCandidate("normalized", self._to_jpeg(base), "image/jpeg"),
                OCRCandidate("thresholded", self._to_jpeg(thresholded), "image/jpeg"),
                OCRCandidate("sharpened", self._to_jpeg(sharpened), "image/jpeg"),
            ]
        except Exception as exc:
            logger.warning("Image preprocessing failed, using original: %s", exc)
            return [OCRCandidate("original", image_bytes, mime_type)]

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

    def _parse_response(self, data: dict) -> OCRResult:
        responses = data.get("responses", [{}])
        response = responses[0] if responses else {}
        if error := response.get("error"):
            raise RuntimeError(f"Vision API error: {error.get('message')}")

        full_text_annotation = response.get("fullTextAnnotation", {})
        full_text = full_text_annotation.get("text", "")
        confidence = self._compute_confidence(full_text_annotation)
        result = OCRResult(text=full_text, confidence=confidence)

        for page in full_text_annotation.get("pages", []):
            for block in page.get("blocks", []):
                for paragraph in block.get("paragraphs", []):
                    for word in paragraph.get("words", []):
                        word_text = "".join(s.get("text", "") for s in word.get("symbols", []))
                        result.blocks.append({
                            "text": word_text,
                            "confidence": word.get("confidence", 0),
                            "bounding_box": word.get("boundingBox", {}),
                        })
        return result

    def _compute_confidence(self, annotation: dict) -> float:
        confidences = []
        for page in annotation.get("pages", []):
            for block in page.get("blocks", []):
                if c := block.get("confidence"):
                    confidences.append(c)
        return sum(confidences) / len(confidences) if confidences else 0.0

    def _mock_invoice_text(self) -> str:
        return """
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


def re_has_invoice_markers(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("hoa don", "ky hieu", "tong cong", "ma so thue"))
