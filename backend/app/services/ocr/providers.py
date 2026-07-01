"""
Shared OCR types and provider factory.

Provides:
- OCRResult: standard result object returned by all OCR providers
- OCRProviderError: raised on provider failure
- get_ocr_provider(): factory that returns the configured provider instance
"""

from dataclasses import dataclass, field
from app.core.config import get_settings


@dataclass
class OCRResult:
    """Standard result from any OCR provider."""
    text: str
    confidence: float
    provider: str = "unknown"
    page_count: int = 1
    blocks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    duration_ms: float = 0.0


class OCRProviderError(Exception):
    """Raised when an OCR provider fails due to credentials, API errors, or timeouts."""

    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(message)
        self.provider = provider


def get_ocr_provider():
    """
    Factory: returns the configured OCR provider based on OCR_ENGINE setting.

    Engines:
        google  — Google Cloud Vision (production default)
        paddle  — PaddleOCR offline fallback
        mock    — deterministic mock for dev/testing

    Usage:
        provider = get_ocr_provider()
        result = await provider.extract_text(image_bytes, "image/jpeg")
    """
    settings = get_settings()
    engine = settings.ocr_engine.lower()

    if engine == "google":
        from app.services.ocr.google_vision import GoogleVisionOCR

        return GoogleVisionOCR(settings)
    elif engine == "paddle":
        from app.services.ocr.vision_service import PaddleOCRProvider

        return PaddleOCRProvider(settings)
    elif engine == "mock":
        from app.services.ocr.vision_service import MockOCRProvider

        return MockOCRProvider(settings)
    else:
        # Unknown engine — warn and fall back to mock
        from app.services.ocr.vision_service import MockOCRProvider

        return MockOCRProvider(settings)
