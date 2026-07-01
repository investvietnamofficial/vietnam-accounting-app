"""
Tests for the OCR provider architecture.

Covers:
- Provider factory selection (google / paddle / mock)
- MockOCRProvider deterministic output
- GoogleVisionOCR credential validation and mocked API calls
- PaddleOCRProvider mocked calls
- OCRResult dataclass fields
- Fallback / error behavior

Tests do NOT call real Google APIs, PaddleOCR, or make network calls.
"""

import json as _json
import sys
import os

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# json alias for use in test bodies
json = _json


# ---------------------------------------------------------------------------
# Import the public API under test
# ---------------------------------------------------------------------------

from app.services.ocr.providers import (
    get_ocr_provider,
    OCRResult,
    OCRProviderError,
)
from app.services.ocr.vision_service import (
    MockOCRProvider,
    PaddleOCRProvider,
    _has_invoice_markers,
    _get_paddleocr,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeSettings:
    """Minimal settings object for provider instantiation."""

    def __init__(
        self,
        ocr_engine: str = "mock",
        paddleocr_lang: str = "vi",
        paddleocr_use_gpu: bool = False,
        paddleocr_timeout_seconds: int = 45,
        google_cloud_project: str = "",
        google_cloud_credentials_json: str = "",
        google_application_credentials: str = "",
        ocr_timeout_seconds: int = 60,
    ):
        self.ocr_engine = ocr_engine
        self.paddleocr_lang = paddleocr_lang
        self.paddleocr_use_gpu = paddleocr_use_gpu
        self.paddleocr_timeout_seconds = paddleocr_timeout_seconds
        self.google_cloud_project = google_cloud_project
        self.google_cloud_credentials_json = google_cloud_credentials_json
        self.google_application_credentials = google_application_credentials
        self.ocr_timeout_seconds = ocr_timeout_seconds


# ---------------------------------------------------------------------------
# Provider factory selection
# ---------------------------------------------------------------------------

def test_get_ocr_provider_mock():
    with patch("app.services.ocr.providers.get_settings") as mock_settings:
        mock_settings.return_value = FakeSettings(ocr_engine="mock")
        provider = get_ocr_provider()
        assert isinstance(provider, MockOCRProvider)


def test_get_ocr_provider_google():
    with patch("app.services.ocr.providers.get_settings") as mock_settings:
        mock_settings.return_value = FakeSettings(ocr_engine="google")
        # Should raise because no credentials are set
        from app.services.ocr.google_vision import GoogleVisionOCR

        provider = get_ocr_provider()
        assert isinstance(provider, GoogleVisionOCR)


def test_get_ocr_provider_paddle():
    with patch("app.services.ocr.providers.get_settings") as mock_settings:
        mock_settings.return_value = FakeSettings(ocr_engine="paddle")
        with patch.dict(sys.modules, {"paddleocr": MagicMock()}):
            provider = get_ocr_provider()
            assert isinstance(provider, PaddleOCRProvider)


def test_get_ocr_provider_unknown_defaults_to_mock():
    with patch("app.services.ocr.providers.get_settings") as mock_settings:
        mock_settings.return_value = FakeSettings(ocr_engine="nonexistent")
        provider = get_ocr_provider()
        assert isinstance(provider, MockOCRProvider)


# ---------------------------------------------------------------------------
# MockOCRProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_ocr_returns_invoice_text():
    provider = MockOCRProvider(FakeSettings())
    result = await provider.extract_text(b"fake-image-bytes", "image/jpeg")

    assert "HOA DON" in result.text
    assert "1C26TAA" in result.text
    assert "5.500.000" in result.text


@pytest.mark.asyncio
async def test_mock_ocr_returns_confidence():
    provider = MockOCRProvider(FakeSettings())
    result = await provider.extract_text(b"fake-image-bytes", "image/png")

    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_mock_ocr_provider_name():
    provider = MockOCRProvider(FakeSettings())
    result = await provider.extract_text(b"", "image/jpeg")

    assert result.provider == "mock"


@pytest.mark.asyncio
async def test_mock_ocr_page_count_is_one():
    provider = MockOCRProvider(FakeSettings())
    result = await provider.extract_text(b"bytes", "application/pdf")

    assert result.page_count == 1


@pytest.mark.asyncio
async def test_mock_ocr_pdf():
    provider = MockOCRProvider(FakeSettings())
    result = await provider.extract_text_from_pdf(b"%PDF-fake")

    assert result.provider == "mock"
    assert "HOA DON" in result.text


# ---------------------------------------------------------------------------
# GoogleVisionOCR — credential validation
# ---------------------------------------------------------------------------

def test_google_creds_json_missing_raises():
    """When GOOGLE_CLOUD_CREDENTIALS_JSON is empty and file doesn't exist, should raise."""
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json="",
        google_application_credentials="/nonexistent/path.json",
        google_cloud_project="test-project",
    )
    # The file doesn't exist so it should raise
    with pytest.raises(OCRProviderError) as exc_info:
        GoogleVisionOCR(settings).client  # trigger lazy init

    assert "not found" in str(exc_info.value).lower()


def test_google_creds_json_placeholder_raises():
    """When GOOGLE_CLOUD_CREDENTIALS_JSON looks like a placeholder, should raise."""
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json="your-google-credentials",
        google_application_credentials="",
    )
    with pytest.raises(OCRProviderError) as exc_info:
        GoogleVisionOCR(settings).client

    assert "credentials" in str(exc_info.value).lower()


def test_google_creds_json_invalid_json_raises():
    """When GOOGLE_CLOUD_CREDENTIALS_JSON is not valid JSON, should raise."""
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json="this is not json {{{",
        google_application_credentials="",
    )
    with pytest.raises(OCRProviderError) as exc_info:
        GoogleVisionOCR(settings).client

    assert "json" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# GoogleVisionOCR — image OCR with mocked API
# ---------------------------------------------------------------------------

def _mock_vision_response(text: str, confidence: float = 0.95) -> MagicMock:
    """Build a mock google.cloud.vision_v1 AnnotateImageResponse."""
    mock_response = MagicMock()
    mock_annotation = MagicMock()
    mock_annotation.text = text
    mock_annotation.pages = [
        MagicMock(
            confidence=confidence,
            blocks=[
                MagicMock(
                    confidence=confidence,
                    paragraphs=[
                        MagicMock(
                            words=[
                                MagicMock(
                                    confidence=confidence,
                                    symbols=[MagicMock(symbol=MagicMock(text="Word"))]
                                )
                            ]
                        )
                    ],
                    bounding_poly=MagicMock(
                        vertices=[MagicMock(x=0, y=0)]
                    ),
                )
            ],
        )
    ]
    mock_response.full_text_annotation = mock_annotation
    return mock_response


@pytest.mark.asyncio
async def test_google_image_ocr_success():
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
        ocr_timeout_seconds=60,
    )

    # Patch at the google-auth level so real key deserialization is skipped
    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("app.services.ocr.google_vision.vision_v1") as mock_vision_module:

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_client_instance = MagicMock()
        mock_vision_module.ImageAnnotatorClient.return_value = mock_client_instance
        mock_client_instance.annotate_image.return_value = _mock_vision_response(
            "HOA DON GIA TRI GIA TANG\n1C26TAA", 0.95
        )

        provider = GoogleVisionOCR(settings)
        # Force client init
        _ = provider.client

        result = await provider.extract_text(b"fake-image-bytes", "image/jpeg")

        assert result.text == "HOA DON GIA TRI GIA TANG\n1C26TAA"
        assert result.provider == "google"
        assert result.page_count == 1
        assert result.confidence == 0.95
        assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_google_image_ocr_returns_blocks():
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("app.services.ocr.google_vision.vision_v1") as mock_vision_module:

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_client = MagicMock()
        mock_vision_module.ImageAnnotatorClient.return_value = mock_client
        mock_client.annotate_image.return_value = _mock_vision_response("Invoice 123", 0.90)

        provider = GoogleVisionOCR(settings)
        _ = provider.client

        result = await provider.extract_text(b"image-bytes", "image/png")

        assert isinstance(result.blocks, list)
        assert len(result.blocks) >= 1


@pytest.mark.asyncio
async def test_google_api_error_raises_ocr_provider_error():
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("app.services.ocr.google_vision.vision_v1") as mock_vision_module:

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_client = MagicMock()
        mock_vision_module.ImageAnnotatorClient.return_value = mock_client
        mock_client.annotate_image.side_effect = Exception("Quota exceeded")

        provider = GoogleVisionOCR(settings)
        _ = provider.client

        with pytest.raises(OCRProviderError) as exc_info:
            await provider.extract_text(b"image", "image/jpeg")

        assert "Quota exceeded" in str(exc_info.value)
        assert exc_info.value.provider == "google"


@pytest.mark.asyncio
async def test_google_timeout_raises():
    """When Vision API takes longer than ocr_timeout_seconds, OCRProviderError is raised."""
    from app.services.ocr.google_vision import GoogleVisionOCR
    import time

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
        ocr_timeout_seconds=1,  # very short timeout
    )

    def slow_annotate(*args, **kwargs):
        time.sleep(5)  # longer than timeout
        return MagicMock()  # won't be reached

    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("app.services.ocr.google_vision.vision_v1") as mock_vision_module:

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_client = MagicMock()
        mock_vision_module.ImageAnnotatorClient.return_value = mock_client
        mock_client.annotate_image = slow_annotate

        provider = GoogleVisionOCR(settings)
        _ = provider.client

        with pytest.raises(OCRProviderError) as exc_info:
            await provider.extract_text(b"image", "image/jpeg")

        assert "timed out" in str(exc_info.value)


# ---------------------------------------------------------------------------
# GoogleVisionOCR — PDF OCR (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_pdf_ocr_multi_page():
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
        ocr_timeout_seconds=60,
    )

    # Mock pdf2image to return 2 pages
    mock_page_1 = MagicMock()
    mock_page_1.mode = "RGB"
    mock_page_1.size = (100, 200)

    mock_page_2 = MagicMock()
    mock_page_2.mode = "RGB"
    mock_page_2.size = (100, 200)

    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("app.services.ocr.google_vision.vision_v1") as mock_vision_module, \
         patch("pdf2image.convert_from_bytes") as mock_convert:

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_client = MagicMock()
        mock_vision_module.ImageAnnotatorClient.return_value = mock_client

        mock_response_page1 = _mock_vision_response("Page 1 content", 0.9)
        mock_response_page2 = _mock_vision_response("Page 2 content", 0.85)

        # Return different responses on successive calls
        mock_client.annotate_image.side_effect = [mock_response_page1, mock_response_page2]

        # pdf2image returns list of PIL Images
        mock_convert.return_value = [mock_page_1, mock_page_2]

        provider = GoogleVisionOCR(settings)
        _ = provider.client

        result = await provider.extract_text_from_pdf(b"%PDF-fake-pdf-content")

        assert result.provider == "google"
        assert result.page_count == 2
        assert "Page 1" in result.text
        assert "Page 2" in result.text
        assert 0.85 <= result.confidence <= 0.95


@pytest.mark.asyncio
async def test_google_pdf_empty_returns_empty():
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        ocr_engine="google",
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("pdf2image.convert_from_bytes") as mock_convert:

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_convert.return_value = []  # empty PDF

        provider = GoogleVisionOCR(settings)
        result = await provider.extract_text_from_pdf(b"%PDF-empty")

        assert result.text == ""
        assert result.page_count == 0


@pytest.mark.asyncio
async def test_google_pdf_pdf2image_missing_raises():
    """When pdf2image raises ImportError, GoogleVisionOCR raises OCRProviderError."""
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(ocr_engine="google")

    # Mock convert_from_bytes to raise ImportError (simulating missing pdf2image)
    with patch("pdf2image.convert_from_bytes", side_effect=ImportError("No module named 'pdf2image'")):
        provider = GoogleVisionOCR(settings)

        with pytest.raises(OCRProviderError) as exc_info:
            await provider.extract_text_from_pdf(b"%PDF-fake")

        assert "pdf2image" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# PaddleOCRProvider (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paddle_ocr_success():
    """PaddleOCR returns OCRResult when ocr() returns structured data."""
    mock_ocr_result = [
        [
            [[[0, 0], [100, 0], [100, 20], [0, 20]], ("Hoa don", 0.9)],
            [[[0, 25], [200, 25], [200, 45], [0, 45]], ("123456", 0.88)],
        ]
    ]

    from app.services.ocr.providers import OCRResult

    settings = FakeSettings(ocr_engine="paddle")
    provider = PaddleOCRProvider(settings)

    # Mock _run_candidates to return a synchronous OCRResult
    # (extract_text awaits it via asyncio.to_thread)
    expected = OCRResult(text="Hoa don\n123456", confidence=0.89, provider="paddle")
    provider._run_candidates = MagicMock(return_value=expected)

    result = await provider.extract_text(b"image-bytes", "image/jpeg")

    assert result.provider == "paddle"
    assert "Hoa don" in result.text
    assert result.confidence > 0


@pytest.mark.asyncio
async def test_paddle_ocr_timeout():
    """PaddleOCR raises OCRProviderError on timeout."""
    import asyncio

    async def slow_run(*args, **kwargs):
        await asyncio.sleep(10)

    with patch.object(PaddleOCRProvider, "_run_candidates", side_effect=asyncio.TimeoutError):
        settings = FakeSettings(ocr_engine="paddle", paddleocr_timeout_seconds=1)
        provider = PaddleOCRProvider(settings)

        with pytest.raises(OCRProviderError) as exc_info:
            await provider.extract_text(b"image", "image/jpeg")

        assert "timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_paddle_ocr_empty_result():
    """PaddleOCR returns empty result on no text."""
    with patch.object(PaddleOCRProvider, "_run_candidates") as mock_run:
        from app.services.ocr.providers import OCRResult

        mock_run.return_value = OCRResult(text="", confidence=0.0, provider="paddle")

        settings = FakeSettings(ocr_engine="paddle")
        provider = PaddleOCRProvider(settings)

        result = await provider.extract_text(b"image", "image/jpeg")

        assert result.text == ""


# ---------------------------------------------------------------------------
# OCRResult dataclass
# ---------------------------------------------------------------------------

def test_ocr_result_defaults():
    result = OCRResult(text="hello", confidence=0.9)

    assert result.text == "hello"
    assert result.confidence == 0.9
    assert result.provider == "unknown"
    assert result.page_count == 1
    assert result.blocks == []
    assert result.warnings == []
    assert result.duration_ms == 0.0


def test_ocr_result_full():
    result = OCRResult(
        text="invoice",
        confidence=0.95,
        provider="google",
        page_count=3,
        blocks=[{"text": "word", "confidence": 0.9}],
        warnings=["Page 2 slow"],
        duration_ms=1500.0,
    )

    assert result.page_count == 3
    assert result.blocks[0]["text"] == "word"
    assert result.warnings[0] == "Page 2 slow"
    assert result.duration_ms == 1500.0


# ---------------------------------------------------------------------------
# OCRProviderError
# ---------------------------------------------------------------------------

def test_ocr_provider_error_message():
    err = OCRProviderError("API key invalid", provider="google")
    assert str(err) == "API key invalid"
    assert err.provider == "google"


# ---------------------------------------------------------------------------
# Full pipeline simulation (mock response)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_mock_response():
    """
    Simulate: OCRResult → downstream processing fields.
    Verifies all fields needed by the document pipeline are present.
    """
    provider = MockOCRProvider(FakeSettings())
    result = await provider.extract_text(b"image-bytes", "image/jpeg")

    # Fields consumed by tasks.py pipeline
    assert isinstance(result.text, str)
    assert isinstance(result.confidence, float)
    assert isinstance(result.provider, str)

    # Extractor receives ocr_result.text and ocr_result.confidence
    ocr_text = result.text
    ocr_confidence = result.confidence

    assert "HOA DON" in ocr_text
    assert 0 <= ocr_confidence <= 1


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def test_has_invoice_markers_true():
    assert _has_invoice_markers("HOA DON GIA TRI GIA TANG") is True
    assert _has_invoice_markers("Ky hieu: 1C26TAA") is True
    assert _has_invoice_markers("Tong cong 5.000.000") is True
    assert _has_invoice_markers("Ma so thue: 0312345678") is True


def test_has_invoice_markers_false():
    assert _has_invoice_markers("Random text without invoice markers") is False
    assert _has_invoice_markers("Hello world") is False


# ---------------------------------------------------------------------------
# Image preprocessing guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_preprocess_falls_back_on_error():
    """When PIL fails during image preprocessing, GoogleVisionOCR falls back to original bytes."""
    from app.services.ocr.google_vision import GoogleVisionOCR

    settings = FakeSettings(
        google_cloud_credentials_json=json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key1",
            "private_key": (
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyf8DqRy3gCqbM\n"
                "-----END RSA PRIVATE KEY-----"
            ),
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
    )

    with patch("google.oauth2.service_account.Credentials") as mock_creds_cls, \
         patch("app.services.ocr.google_vision.vision_v1") as mock_vision_module:
        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_file.return_value = mock_creds

        mock_client = MagicMock()
        mock_vision_module.ImageAnnotatorClient.return_value = mock_client
        mock_client.annotate_image.return_value = _mock_vision_response("OK", 0.9)

        provider = GoogleVisionOCR(settings)
        _ = provider.client

        # If PIL fails during preprocessing, it should fall back to original bytes
        with patch("PIL.Image.open") as mock_open:
            mock_open.side_effect = Exception("Corrupt image")

            result = await provider.extract_text(b"some-bytes", "image/jpeg")

            # Should still get a result (fallback path)
            assert result.provider == "google"


# ---------------------------------------------------------------------------
# Credential placeholder detection
# ---------------------------------------------------------------------------

def test_is_placeholder_recognition():
    from app.services.ocr.google_vision import _is_placeholder

    assert _is_placeholder("") is True
    assert _is_placeholder("your-google-credentials") is True
    assert _is_placeholder("YOUR-GOOGLE-KEY") is True
    assert _is_placeholder("changeme") is True
    assert _is_placeholder("paste") is True
    assert _is_placeholder("Enter your credentials") is True
    assert _is_placeholder("null") is True
    assert _is_placeholder("none") is True
    assert _is_placeholder("real-project-456") is False
    assert _is_placeholder('{"type":"service_account"}') is False
