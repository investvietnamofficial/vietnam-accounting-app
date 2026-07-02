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


# M-2: Send password-reset email as a background Celery task to avoid blocking
# the HTTP response. Falls back to inline send when Celery is not configured.
@celery_app.task(
    bind=True,
    name="app.workers.tasks.send_email",
    max_retries=3,
    default_retry_delay=30,
)
def send_email_task(self, to_email: str, reset_token: str):
    """Send a password-reset email asynchronously via Celery."""
    from app.services.email.email_service import get_email_service
    try:
        get_email_service().send_password_reset_email(to_email, reset_token)
        logger.info("send_email_celery_task_success", to=to_email)
    except Exception as exc:
        logger.error("send_email_celery_task_failed", to=to_email, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, name="verify-einvoice-async", max_retries=5, default_retry_delay=60)
def verify_einvoice_async(self, invoice_id: str):
    """Background re-verification of an invoice against the GDT portal.

    B-1 fix: uses AsyncSessionLocal (same pattern as _process_document_async),
    no hardcoded filesystem paths, runs correctly in Docker.
    """
    return _run_verify_einvoice_async(self, invoice_id)


def _run_verify_einvoice_async(task, invoice_id: str):
    """Sync wrapper — Celery calls this; runs the async logic in a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_verify_einvoice_async_inner(task, invoice_id))
    finally:
        loop.close()


async def _verify_einvoice_async_inner(task, invoice_id: str):
    """Async implementation — uses AsyncSessionLocal, no hardcoded paths."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models import Invoice
    from app.services.einvoice import GDTInvoiceVerificationService

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
            inv = result.scalar_one_or_none()
            if not inv:
                return {"status": "error", "invoice_id": invoice_id}

            # H-1 fix: pass primitive arguments, not the ORM object
            gdt = GDTInvoiceVerificationService()
            result = await gdt.verify_invoice(
                invoice_series=inv.invoice_series,
                invoice_number=inv.invoice_number,
                tax_code=inv.seller_tax_code or inv.buyer_tax_code,
            )

            inv.einvoice_verified = result.get("verified", False)
            inv.einvoice_verified_at = datetime.now(UTC)
            inv.einvoice_verification_data = result
            await db.commit()
            return {"status": "ok", "invoice_id": invoice_id}

        except Exception as exc:
            await db.rollback()
            countdown = 60 * (task.request.retries + 1)
            raise task.retry(exc=exc, countdown=countdown)


async def process_document_now(document_id: str):
    """Inline processing path for local MVP usage without a Celery worker."""
    return await _process_document_async(None, document_id)


async def _process_document_async(task, document_id: str):
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models import Company, DirectionStatus, Document, DocumentStatus, Invoice
    from app.api.routes.reports import _invoice_direction
    from app.services.einvoice import GDTInvoiceVerificationService
    from app.services.extraction.claude_extractor import ExtractionService
    from app.services.ocr.providers import get_ocr_provider
    from app.services.storage.r2_service import R2Service

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        echo=False,
    )
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            logger.error("document_not_found", document_id=document_id)
            return {"status": "error", "message": "Document not found"}

        # Guard: if document already has an invoice, skip processing
        # (prevents duplicate invoices when same checksum is re-uploaded while
        # a prior pipeline run is in-progress or was already completed)
        existing_invoice = await db.execute(
            select(Invoice).where(Invoice.document_id == doc.id)
        )
        if existing_invoice.scalar_one_or_none():
            logger.info("document_already_processed", document_id=document_id,
                        reason="existing_invoice_found")
            doc.status = DocumentStatus.EXTRACTED
            await db.commit()
            return {"status": "skipped", "document_id": document_id,
                    "reason": "existing_invoice_found"}

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

            # Warn if PDF is very large before OCR
            if doc.mime_type == "application/pdf":
                page_count_est = _estimate_pdf_pages(raw_bytes)
                if page_count_est and page_count_est > MAX_PDF_PAGES:
                    logger.warning(
                        "large_pdf_capped",
                        document_id=document_id,
                        estimated_pages=page_count_est,
                        capped_pages=MAX_PDF_PAGES,
                    )
                    doc.ocr_warnings = (doc.ocr_warnings or []) + [
                        f"PDF has ~{page_count_est} pages, only first {MAX_PDF_PAGES} will be processed."
                    ]

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

            # H-5: Determine and store invoice direction at extraction time
            direction = None
            direction_status = DirectionStatus.UNKNOWN
            direction_confidence = None
            if doc.company_id:
                co_result = await db.execute(select(Company).where(Company.id == doc.company_id))
                company = co_result.scalar_one_or_none()
                if company:
                    # Build a minimal invoice-like dict from extracted data for direction logic
                    _fake_inv = type("FakeInv", (), {
                        "seller_tax_code": extracted.get("seller_tax_code"),
                        "buyer_tax_code": extracted.get("buyer_tax_code"),
                        "invoice_series": extracted.get("invoice_series"),
                        "invoice_number": extracted.get("invoice_number"),
                        "invoice_date": extracted.get("invoice_date"),
                    })()
                    direction, is_certain = _invoice_direction(_fake_inv, company)
                    direction_status = DirectionStatus.INFERRED if is_certain else DirectionStatus.UNKNOWN
                    direction_confidence = 1.0 if is_certain else 0.5

            if invoice is None:
                # M-5 + H-4: Handle concurrent upload race — if another process already
                # created the invoice for the same (company, series, number), reuse it.
                try:
                    new_invoice = Invoice(
                        company_id=doc.company_id,
                        document_id=doc.id,
                        # H-5: direction fields populated at extraction time
                        invoice_direction=direction,
                        direction_status=direction_status,
                        direction_confidence=direction_confidence,
                    )
                    db.add(new_invoice)
                    await db.flush()  # flush to trigger constraint before commit
                    invoice = new_invoice
                except Exception as exc:
                    # Check if it's an integrity violation from the unique constraint
                    if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                        await db.rollback()
                        # Fetch the existing invoice that caused the constraint violation
                        existing = await db.execute(
                            select(Invoice).where(
                                Invoice.company_id == doc.company_id,
                                Invoice.invoice_series == extracted.get("invoice_series"),
                                Invoice.invoice_number == extracted.get("invoice_number"),
                            )
                        )
                        invoice = existing.scalar_one_or_none()
                        if invoice is None:
                            raise  # re-raise if we can't find it (different error)
                    else:
                        raise

            invoice.invoice_series = extracted.get("invoice_series")
            invoice.invoice_number = extracted.get("invoice_number")
            invoice.invoice_date = _parse_invoice_date(extracted.get("invoice_date"))
            invoice.invoice_type = extracted.get("invoice_type") or doc.doc_type
            # currency_code: default VND; non-VND is flagged at extraction validation
            # M-8: currency extraction with FX support
            currency_code = extracted.get("currency_code", "VND")
            exchange_rate = extracted.get("exchange_rate_estimate")
            converted_vnd = extracted.get("converted_vnd_amount")
            invoice.currency_code = currency_code
            if exchange_rate is not None:
                invoice.exchange_rate = float(exchange_rate)
                invoice.exchange_source = "extraction_estimate"
            if converted_vnd is not None:
                invoice.converted_vnd_amount = int(converted_vnd)
            elif currency_code == "VND":
                invoice.converted_vnd_amount = invoice.total_amount
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
            # H-3: propagate extraction confidence from document to invoice
            invoice.extraction_confidence = doc.extraction_confidence
            # H-5: also set direction fields on existing invoices (race condition path)
            invoice.invoice_direction = direction
            invoice.direction_status = direction_status
            invoice.direction_confidence = direction_confidence

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


MAX_PDF_PAGES = 30  # cap to prevent OOM on large PDFs


def _estimate_pdf_pages(content: bytes) -> int | None:
    """Quick estimate of PDF page count without full rendering."""
    try:
        import io
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            return len(reader.pages)
        except ImportError:
            pass
        # Fallback: count /Page objects in raw bytes (approximate)
        import re
        matches = re.findall(rb"/Type\s*/Page[^s]", content)
        return len(matches) if matches else None
    except Exception:
        return None


def _prepare_document_for_ocr(content: bytes, mime_type: str) -> bytes:
    """Convert document to image bytes for OCR. Processes all PDF pages (capped at MAX_PDF_PAGES)."""
    if mime_type != "application/pdf":
        return content

    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pdf2image is required to process PDF uploads") from exc

    pages = convert_from_bytes(content, first_page=1, last_page=MAX_PDF_PAGES, fmt="jpeg")
    if not pages:
        raise RuntimeError("PDF conversion produced no pages")

    # Combine all pages into a single byte stream, separated by page markers
    result = b""
    for page in pages:
        if page.mode != "RGB":
            page = page.convert("RGB")
        buf = BytesIO()
        page.save(buf, format="JPEG", quality=85)
        result += buf.getvalue()
        result += b"\n--- PAGE BREAK ---\n"
    return result
