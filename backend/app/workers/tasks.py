"""
Celery tasks — document processing pipeline.
"""

import asyncio
import json
from datetime import UTC, datetime
from io import BytesIO

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=10,
)
def process_document(self, document_id: str):
    """Process an uploaded document through OCR, extraction, and verification."""
    return run_async(_process_document_async(self, document_id))


async def process_document_now(document_id: str):
    """Inline processing path for local MVP usage without a Celery worker."""
    return await _process_document_async(None, document_id)


async def _process_document_async(task, document_id: str):
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import Document, DocumentStatus, Invoice
    from app.services.einvoice import GDTInvoiceVerificationService
    from app.services.extraction.claude_extractor import ExtractionService
    from app.services.ocr.providers import get_ocr_provider
    from app.services.storage.r2_service import R2Service

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            logger.error("document_not_found", document_id=document_id)
            return {"status": "error", "message": "Document not found"}

        try:
            doc.processing_attempts = (doc.processing_attempts or 0) + 1
            doc.status = DocumentStatus.PROCESSING
            doc.processing_error = None
            doc.processing_started_at = datetime.now(UTC)
            await db.commit()

            logger.info(
                "document_processing_started",
                document_id=document_id,
                attempts=doc.processing_attempts,
                mime_type=doc.mime_type,
                file_size_bytes=len(doc.file_url.encode()) if doc.file_url else 0,
            )

            r2 = R2Service()
            raw_bytes = await r2.download(doc.file_url)

            ocr_provider = get_ocr_provider()
            # Use PDF method for PDFs if available, otherwise fall back to image method
            if doc.mime_type == "application/pdf" and hasattr(ocr_provider, "extract_text_from_pdf"):
                ocr_result = await ocr_provider.extract_text_from_pdf(raw_bytes)
            else:
                image_bytes = _prepare_document_for_ocr(raw_bytes, doc.mime_type)
                ocr_result = await ocr_provider.extract_text(image_bytes, doc.mime_type)

            # Persist all OCR metadata
            doc.ocr_raw_text = ocr_result.text
            doc.ocr_confidence = ocr_result.confidence
            doc.ocr_provider = ocr_result.provider
            doc.ocr_duration_ms = int(ocr_result.duration_ms)
            doc.ocr_page_count = ocr_result.page_count
            doc.ocr_language = "vi+en"  # current language hints used by all providers
            doc.ocr_engine_version = getattr(ocr_provider, "ENGINE_VERSION", ocr_result.provider)
            doc.ocr_warnings = ocr_result.warnings or None
            # Serialise pages: OCRPage -> plain dict for JSONB
            doc.ocr_pages = [
                {"page_number": p.page_number, "text": p.text, "confidence": p.confidence}
                for p in ocr_result.pages
            ] if ocr_result.pages else None

            extractor = ExtractionService()
            extracted = await extractor.extract_invoice_fields(
                ocr_result.text,
                doc_type_hint=doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type),
                ocr_confidence=float(ocr_result.confidence or 0),
            )
            doc.extracted_data = extracted
            doc.extraction_confidence = extracted.get("confidence", 0)
            doc.status = DocumentStatus.EXTRACTED

            invoice_result = await db.execute(select(Invoice).where(Invoice.document_id == doc.id))
            invoice = invoice_result.scalar_one_or_none()
            if invoice is None:
                invoice = Invoice(company_id=doc.company_id, document_id=doc.id)
                db.add(invoice)

            invoice.invoice_series = extracted.get("invoice_series")
            invoice.invoice_number = extracted.get("invoice_number")
            invoice.invoice_date = _parse_invoice_date(extracted.get("invoice_date"))
            invoice.invoice_type = extracted.get("invoice_type") or doc.doc_type
            invoice.seller_name = extracted.get("seller_name")
            invoice.seller_tax_code = extracted.get("seller_tax_code")
            invoice.seller_address = extracted.get("seller_address")
            invoice.buyer_name = extracted.get("buyer_name")
            invoice.buyer_tax_code = extracted.get("buyer_tax_code")
            invoice.buyer_address = extracted.get("buyer_address")
            invoice.subtotal_amount = extracted.get("subtotal_amount") or 0
            invoice.vat_rate = _parse_vat_rate(extracted.get("vat_rate"))
            invoice.vat_amount = extracted.get("vat_amount") or 0
            invoice.total_amount = extracted.get("total_amount") or 0
            invoice.line_items = extracted.get("line_items", [])
            invoice.einvoice_code = extracted.get("einvoice_code")
            invoice.notes = extracted.get("notes")

            doc.processed_at = datetime.now(UTC)
            await db.commit()

            await _verify_invoice_with_gdt(db, invoice)

            logger.info(
                "document_processing_succeeded",
                document_id=document_id,
                invoice_id=invoice.id,
                attempts=doc.processing_attempts,
                ocr_provider=doc.ocr_provider,
                ocr_duration_ms=doc.ocr_duration_ms,
                ocr_page_count=doc.ocr_page_count,
                ocr_confidence=doc.ocr_confidence,
                extraction_confidence=doc.extraction_confidence,
            )
            return {"status": "success", "document_id": document_id, "invoice_id": invoice.id}

        except Exception as exc:
            retry_scheduled = _should_retry(task)
            doc.processing_error = str(exc)
            doc.processed_at = datetime.now(UTC)
            doc.status = DocumentStatus.PENDING if retry_scheduled else DocumentStatus.FAILED
            await db.commit()
            logger.warning(
                "document_processing_failed",
                document_id=document_id,
                attempts=doc.processing_attempts,
                retry_scheduled=retry_scheduled,
                ocr_provider=getattr(doc, "ocr_provider", None),
                error=str(exc),
            )
            if retry_scheduled and task is not None:
                raise task.retry(exc=exc)
            raise


def _parse_invoice_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_vat_rate(value):
    from app.models import VATRate

    try:
        return VATRate(str(value))
    except ValueError:
        return VATRate.TEN


async def _verify_invoice_with_gdt(db, invoice):
    """Verify invoice via GDT API without failing the entire document pipeline."""
    from app.services.einvoice import GDTInvoiceVerificationService

    if not (invoice.invoice_series and invoice.invoice_number):
        invoice.notes = (invoice.notes or "") + "\nGDT verify skipped: missing invoice series/number."
        await db.commit()
        return

    try:
        service = GDTInvoiceVerificationService()
        result = await service.verify_invoice(
            invoice_series=invoice.invoice_series,
            invoice_number=invoice.invoice_number,
            tax_code=invoice.seller_tax_code or invoice.buyer_tax_code,
        )

        invoice.einvoice_verified = result.get("verified", False)
        invoice.notes = (invoice.notes or "") + "\nGDT verify result: " + json.dumps(result, ensure_ascii=False)
        if result.get("verified"):
            invoice.einvoice_verified_at = datetime.now(UTC)
        else:
            invoice.einvoice_verified_at = None
        await db.commit()
    except Exception as exc:
        invoice.einvoice_verified = False
        invoice.einvoice_verified_at = None
        invoice.notes = (invoice.notes or "") + f"\nGDT verify error: {exc}"
        await db.commit()


def _should_retry(task) -> bool:
    if task is None:
        return False
    max_retries = getattr(task, "max_retries", 0) or 0
    current_retries = getattr(getattr(task, "request", None), "retries", 0)
    return current_retries < max_retries


def _prepare_document_for_ocr(content: bytes, mime_type: str) -> bytes:
    if mime_type != "application/pdf":
        return content

    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pdf2image is required to process PDF uploads") from exc

    pages = convert_from_bytes(content, first_page=1, last_page=1, fmt="jpeg")
    if not pages:
        raise RuntimeError("PDF conversion produced no pages")

    buf = BytesIO()
    first_page = pages[0]
    if first_page.mode != "RGB":
        first_page = first_page.convert("RGB")
    first_page.save(buf, format="JPEG", quality=95)
    return buf.getvalue()
