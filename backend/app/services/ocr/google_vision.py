"""
Google Cloud Vision OCR provider.

Supports credentials via:
  1. GOOGLE_CLOUD_CREDENTIALS_JSON  — paste full service-account JSON as string env var
  2. GOOGLE_APPLICATION_CREDENTIALS — path to credentials JSON file on disk
  3. Application Default Credentials (ADC) — fallback when neither is set

Set GOOGLE_CLOUD_PROJECT so the SDK knows which project to bill.

Usage:
    from app.services.ocr.providers import get_ocr_provider
    provider = get_ocr_provider()   # returns GoogleVisionOCR when OCR_ENGINE=google
    result = await provider.extract_text(image_bytes, "image/jpeg")
    result = await provider.extract_text_from_pdf(pdf_bytes)
"""

import base64
import io
import json
import logging
import time
from dataclasses import dataclass, field

from app.services.ocr.providers import OCRProviderError, OCRResult

logger = logging.getLogger(__name__)

# Pre-check: try importing google-cloud-vision; raise early if missing
try:
    from google.cloud import vision_v1
    from google.cloud.vision_v1 import types
    from google.protobuf.json_format import ParseDict
except ImportError as exc:  # pragma: no cover — defensive
    raise ImportError(
        "google-cloud-vision is not installed. "
        "Install it with: pip install google-cloud-vision"
    ) from exc


@dataclass
class GoogleVisionOCR:
    """
    Google Cloud Vision OCR provider.

    Args:
        settings: app.core.config.Settings instance
    """

    settings: object
    _client: object = field(default=None, init=False, repr=False)

    # Maximum image dimension (width or height) to stay within Vision API limits
    MAX_IMAGE_DIM: int = 4096
    # Vision API max image size is 20MB
    MAX_IMAGE_BYTES: int = 20 * 1024 * 1024

    # Vision API feature types we request
    DOCUMENT_FEATURE = {"type": "DOCUMENT_TEXT_DETECTION"}

    @property
    def client(self):
        """Lazy-initialise the Vision API client with credentials."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self):
        """
        Build ImageAnnotatorClient, trying credentials in priority order:
          1. GOOGLE_CLOUD_CREDENTIALS_JSON  (string env var with JSON)
          2. GOOGLE_APPLICATION_CREDENTIALS  (path to JSON file)
          3. Application Default Credentials  (ADC — gcloud, workload identity, etc.)
        """
        creds_json = getattr(self.settings, "google_cloud_credentials_json", "") or ""
        creds_path = getattr(self.settings, "google_application_credentials", "") or ""
        project_id = getattr(self.settings, "google_cloud_project", "") or ""

        # Option 1: JSON string from env (easiest for Cloudify/Docker env-var paste)
        if creds_json and creds_json.strip() and not _is_placeholder(creds_json):
            try:
                creds_dict = json.loads(creds_json)
                creds = _build_credentials_from_dict(creds_dict)
                client = vision_v1.ImageAnnotatorClient(credentials=creds)
                logger.info("google_vision_initialized", method="GOOGLE_CLOUD_CREDENTIALS_JSON")
                return _ProjectAwareClient(client, project_id)
            except (json.JSONDecodeError, TypeError) as exc:
                raise OCRProviderError(
                    f"GOOGLE_CLOUD_CREDENTIALS_JSON is not valid JSON: {exc}",
                    provider="google",
                )

        # Option 2: credentials file path
        if creds_path and not _is_placeholder(creds_path):
            import os

            if os.path.exists(creds_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
                client = vision_v1.ImageAnnotatorClient()
                logger.info("google_vision_initialized", method="GOOGLE_APPLICATION_CREDENTIALS")
                return _ProjectAwareClient(client, project_id)
            else:
                raise OCRProviderError(
                    f"GOOGLE_APPLICATION_CREDENTIALS file not found: {creds_path}",
                    provider="google",
                )

        # Option 3: Application Default Credentials (ADC)
        # Works when running on GCP (Cloud Run, GCE, GKE) or after `gcloud auth application-default login`
        try:
            client = vision_v1.ImageAnnotatorClient()
            logger.info("google_vision_initialized", method="ADC")
            return _ProjectAwareClient(client, project_id)
        except Exception as exc:
            raise OCRProviderError(
                "Google Cloud Vision credentials not found. "
                "Set GOOGLE_CLOUD_CREDENTIALS_JSON (recommended for Cloudify) "
                "or GOOGLE_APPLICATION_CREDENTIALS (path to service-account JSON).",
                provider="google",
            ) from exc

    async def extract_text(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> OCRResult:
        """
        Extract text from an image using Google Cloud Vision DOCUMENT_TEXT_DETECTION.

        Args:
            image_bytes: raw image bytes
            mime_type: image MIME type (used to set encoding hint)

        Returns:
            OCRResult with text, confidence, blocks, page_count=1, provider="google"

        Raises:
            OCRProviderError on credentials failure, API error, or timeout
        """
        start = time.monotonic()

        try:
            # Preprocess: resize large images to stay within API limits
            image_bytes = self._prepare_image(image_bytes, mime_type)

            # Encode to base64 for the Vision API
            b64_content = base64.b64encode(image_bytes).decode("utf-8")

            image = types.Image(content=b64_content)
            features = [types.Feature(type=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)]
            request = types.AnnotateImageRequest(image=image, features=features)

            # Call synchronously in a thread pool to avoid blocking the event loop
            import asyncio

            response = await asyncio.wait_for(
                asyncio.to_thread(self.client.annotate_image, request),
                timeout=getattr(self.settings, "ocr_timeout_seconds", 60),
            )

            duration_ms = (time.monotonic() - start) * 1000
            return self._parse_response(response, duration_ms)

        except asyncio.TimeoutError:
            raise OCRProviderError(
                f"Google Vision OCR timed out after {getattr(self.settings, 'ocr_timeout_seconds', 60)}s",
                provider="google",
            )
        except Exception as exc:
            if isinstance(exc, OCRProviderError):
                raise
            raise OCRProviderError(str(exc), provider="google") from exc

    async def extract_text_from_pdf(self, pdf_bytes: bytes) -> OCRResult:
        """
        Extract text from a PDF by converting each page to an image and
        running DOCUMENT_TEXT_DETECTION per page.

        Args:
            pdf_bytes: raw PDF bytes

        Returns:
            OCRResult with merged text from all pages,
            page_count reflecting the number of pages processed

        Raises:
            OCRProviderError on failure
        """
        start = time.monotonic()

        try:
            pages = await self._pdf_to_images(pdf_bytes)
        except Exception as exc:
            if isinstance(exc, OCRProviderError):
                raise
            raise OCRProviderError(f"Failed to convert PDF to images: {exc}", provider="google") from exc

        if not pages:
            return OCRResult(
                text="",
                confidence=0.0,
                provider="google",
                page_count=0,
                duration_ms=(time.monotonic() - start) * 1000,
            )

        all_blocks: list[dict] = []
        page_texts: list[str] = []
        confidences: list[float] = []
        warnings: list[str] = []

        import asyncio

        timeout = getattr(self.settings, "ocr_timeout_seconds", 60)
        per_page_timeout = max(timeout / len(pages), 5)

        for i, (page_bytes, page_num) in enumerate(pages):
            try:
                b64_content = base64.b64encode(page_bytes).decode("utf-8")
                image = types.Image(content=b64_content)
                features = [types.Feature(type=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)]
                request = types.AnnotateImageRequest(image=image, features=features)

                response = await asyncio.wait_for(
                    asyncio.to_thread(self.client.annotate_image, request),
                    timeout=per_page_timeout,
                )

                page_result = self._parse_single_response(response)
                page_texts.append(f"[--- Page {page_num} ---]\n{page_result.text}")
                confidences.append(page_result.confidence)
                all_blocks.extend(page_result.blocks)

            except asyncio.TimeoutError:
                warnings.append(f"Page {page_num} timed out after {per_page_timeout:.0f}s")
            except Exception as exc:
                warnings.append(f"Page {page_num} failed: {exc}")

        merged_text = "\n\n".join(page_texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        duration_ms = (time.monotonic() - start) * 1000

        return OCRResult(
            text=merged_text,
            confidence=avg_confidence,
            provider="google",
            page_count=len(pages),
            blocks=all_blocks,
            warnings=warnings,
            duration_ms=duration_ms,
        )

    def _prepare_image(self, image_bytes: bytes, mime_type: str) -> bytes:
        """
        Resize oversized images and convert to JPEG to stay within Vision API limits.
        Google Vision API max image is 20MB and 4096px max dimension.
        """
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Resize if too large
            w, h = img.size
            if max(w, h) > self.MAX_IMAGE_DIM:
                scale = self.MAX_IMAGE_DIM / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.LANCZOS)

            # Compress if still too large
            if len(image_bytes) > self.MAX_IMAGE_BYTES:
                quality = 85
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality)
                while buf.tell() > self.MAX_IMAGE_BYTES and quality > 40:
                    quality -= 5
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality)

                img_bytes = buf.getvalue()
                if len(img_bytes) < len(image_bytes):
                    return img_bytes

            # Return JPEG if not already
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return buf.getvalue()

        except Exception:
            # If anything goes wrong with preprocessing, return original
            return image_bytes

    async def _pdf_to_images(self, pdf_bytes: bytes) -> list[tuple[bytes, int]]:
        """
        Convert PDF bytes to a list of (JPEG image bytes, page_number) tuples.
        Uses pdf2image (poppler) — falls back to a warning if not available.
        """
        try:
            from pdf2image import convert_from_bytes
        except ImportError:  # pragma: no cover
            raise OCRProviderError(
                "pdf2image is required for PDF OCR but is not installed. "
                "Install with: pip install pdf2image",
                provider="google",
            )

        try:
            pages = convert_from_bytes(
                pdf_bytes,
                dpi=200,
                fmt="jpeg",
                thread_count=2,
            )

            result: list[tuple[bytes, int]] = []
            for i, page_img in enumerate(pages, start=1):
                buf = io.BytesIO()
                # Ensure RGB before JPEG
                if page_img.mode not in ("RGB",):
                    page_img = page_img.convert("RGB")
                page_img.save(buf, format="JPEG", quality=85)
                result.append((buf.getvalue(), i))

            return result

        except Exception as exc:
            raise OCRProviderError(f"pdf2image failed to convert PDF: {exc}", provider="google") from exc

    def _parse_response(self, response, duration_ms: float) -> OCRResult:
        """
        Parse an AnnotateImageResponse (from image OCR) into OCRResult.
        """
        page_result = self._parse_single_response(response)
        return OCRResult(
            text=page_result.text,
            confidence=page_result.confidence,
            provider="google",
            page_count=1,
            blocks=page_result.blocks,
            duration_ms=duration_ms,
        )

    def _parse_single_response(self, response) -> OCRResult:
        """Parse response text and confidence from a Vision API response."""
        annotation = response.full_text_annotation

        if not annotation or not annotation.text:
            return OCRResult(text="", confidence=0.0, provider="google")

        # Compute average block confidence
        confidences: list[float] = []
        blocks: list[dict] = []

        for page in annotation.pages or []:
            page_conf = getattr(page, "confidence", None) or 0.0
            if page_conf > 0:
                confidences.append(page_conf)

            for block in getattr(page, "blocks", []) or []:
                block_conf = getattr(block, "confidence", None) or 0.0
                if block_conf > 0:
                    confidences.append(block_conf)

                block_words: list[dict] = []
                for para in getattr(block, "paragraphs", []) or []:
                    for word in getattr(para, "words", []) or []:
                        word_text = "".join(
                            s.symbol.text for s in getattr(word, "symbols", []) or []
                        )
                        word_conf = getattr(word, "confidence", None) or 0.0
                        if word_text:
                            block_words.append({
                                "text": word_text,
                                "confidence": word_conf,
                            })

                if block_words:
                    blocks.append({
                        "confidence": block_conf,
                        "words": block_words,
                        "bounding_box": _pb_to_dict(getattr(block, "bounding_poly", None)),
                    })

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return OCRResult(
            text=annotation.text,
            confidence=avg_conf,
            provider="google",
            blocks=blocks,
        )


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _is_placeholder(value: str) -> bool:
    """Return True if value looks like an unfilled credential placeholder."""
    if not value:
        return True
    stripped = value.strip().lower()
    return (
        stripped.startswith("your-")
        or stripped in ("none", "null", "changeme", "paste")
        or "enter your" in stripped
        or "placeholder" in stripped
    )


def _build_credentials_from_dict(creds_dict: dict):
    """Build a google.auth.credentials.Credentials from a dict."""
    import tempfile, os

    # Write dict to a temp file so google-auth can read it
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(creds_dict, f)
        return _credentials_from_file(path)
    except Exception:
        os.unlink(path)
        raise


def _credentials_from_file(path: str):
    """Load google-auth credentials from a JSON file path."""
    try:
        import google.auth
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(path)
    except ImportError:  # pragma: no cover
        # Fallback: rely on GOOGLE_APPLICATION_CREDENTIALS env var
        import os

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        return None


def _pb_to_dict(pb) -> dict:
    """Convert a protobuf message to a plain dict (for bounding boxes)."""
    if pb is None:
        return {}
    try:
        return {
            "vertices": [
                {"x": v.x, "y": v.y}
                for v in getattr(pb, "vertices", []) or []
            ]
        }
    except Exception:
        return {}


class _ProjectAwareClient:
    """Wrapper that carries the project_id alongside the Vision client."""

    def __init__(self, client, project_id: str = ""):
        self._client = client
        self._project_id = project_id

    def annotate_image(self, request, **kwargs):
        return self._client.annotate_image(request=request, **kwargs)

    def async_batch_annotate_files(self, requests, **kwargs):
        return self._client.async_batch_annotate_files(requests=requests, **kwargs)

    @property
    def project_id(self) -> str:
        return self._project_id
