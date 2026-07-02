"""
Documents API — upload invoices, poll processing status, list documents.
"""

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Document, DocumentStatus, DocumentType
from app.services.storage.r2_service import R2Service
from app.workers.tasks import process_document, process_document_now

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "application/pdf",
}
MAX_FILE_SIZE_MB = 20


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File(description="Invoice image or PDF")],
    background_tasks: BackgroundTasks,
    doc_type: Annotated[str, Form()] = "other",
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload an invoice document for processing.

    Returns immediately with a job_id.
    Poll GET /documents/{id} to check processing status.
    """
    content = await file.read()
    detected_mime = _detect_mime_type(content)

    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type {detected_mime} not supported. Use JPEG, PNG, WEBP, HEIC, or PDF.",
        )

    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {MAX_FILE_SIZE_MB}MB.",
        )

    checksum = hashlib.sha256(content).hexdigest()
    existing = await _find_existing_document(db, current_user.company_id, checksum)
    if existing:
        logger.info("duplicate_document_upload", extra={"document_id": existing.id, "company_id": current_user.company_id})
        if existing.status in {DocumentStatus.FAILED, DocumentStatus.PENDING}:
            existing.status = DocumentStatus.PENDING
            existing.processing_error = None
            existing.processed_at = None
            job_id = await _dispatch_processing(existing, background_tasks)
            await db.commit()
            return {
                "document_id": existing.id,
                "job_id": job_id,
                "status": existing.status.value,
                "duplicate": True,
                "message": "Existing document re-queued for processing.",
            }
        return {
            "document_id": existing.id,
            "job_id": existing.celery_job_id,
            "status": existing.status.value,
            "duplicate": True,
            "message": "Duplicate upload detected. Reusing the existing document record.",
        }

    r2 = R2Service()
    # Sanitize filename: remove path traversal components and non-printable chars.
    # The UUID prefix in the storage key prevents collisions regardless.
    original_filename = file.filename or "uploaded-document"
    try:
        from werkzeug.utils import secure_filename
        filename = secure_filename(original_filename) or "uploaded-document"
    except Exception:
        # Fallback: strip path components manually
        import re
        filename = re.sub(r"[^a-zA-Z0-9._-]", "_", original_filename.split("/")[-1].split("\\")[-1])
        filename = filename or "uploaded-document"
    file_url = await r2.upload(
        content=content,
        filename=filename,
        mime_type=detected_mime,
        folder=f"companies/{current_user.company_id}/documents",
    )

    doc = Document(
        company_id=current_user.company_id,
        uploaded_by_id=current_user.id,
        file_name=filename,
        file_url=file_url,
        file_size_bytes=len(content),
        mime_type=detected_mime,
        file_checksum=checksum,
        doc_type=_parse_doc_type(doc_type),
        status=DocumentStatus.PENDING,
    )
    db.add(doc)
    await db.flush()

    job_id = await _dispatch_processing(doc, background_tasks)
    await db.commit()

    return {
        "document_id": doc.id,
        "job_id": job_id,
        "status": doc.status.value,
        "message": "Document uploaded. Processing started.",
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document with current processing status and extracted data."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == current_user.company_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return _document_payload(doc)


@router.get("/")
async def list_documents(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents for the current company."""
    query = select(Document).where(Document.company_id == current_user.company_id)

    if status_filter:
        try:
            query = query.where(Document.status == DocumentStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")

    query = query.order_by(Document.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    docs = result.scalars().all()

    return {
        "page": page,
        "page_size": page_size,
        "items": [_document_list_item(d) for d in docs],
    }


@router.post("/{document_id}/retry")
async def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == current_user.company_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status not in {DocumentStatus.FAILED, DocumentStatus.REJECTED}:
        raise HTTPException(status_code=409, detail="Only failed or rejected documents can be retried")
    if doc.duplicate_of_document_id:
        raise HTTPException(status_code=409, detail="Duplicate records cannot be retried directly")

    doc.status = DocumentStatus.PENDING
    doc.processing_error = None
    doc.processed_at = None
    job_id = await _dispatch_processing(doc, background_tasks)
    await db.commit()

    return {
        "document_id": doc.id,
        "job_id": job_id,
        "status": doc.status.value,
        "message": "Document retry queued.",
    }


def _parse_doc_type(value: str) -> DocumentType:
    try:
        return DocumentType(value)
    except ValueError:
        return DocumentType.OTHER


async def _find_existing_document(db: AsyncSession, company_id: str, checksum: str) -> Document | None:
    result = await db.execute(
        select(Document)
        .where(Document.company_id == company_id, Document.file_checksum == checksum)
        .where(Document.duplicate_of_document_id.is_(None))
        .order_by(Document.created_at.desc())
    )
    return result.scalar_one_or_none()


async def _dispatch_processing(doc: Document, background_tasks: BackgroundTasks) -> str:
    if settings.use_celery:
        job = process_document.delay(doc.id)
        doc.celery_job_id = job.id
        return job.id

    job_id = f"local-{doc.id}"
    doc.celery_job_id = job_id
    background_tasks.add_task(process_document_now, doc.id)
    return job_id


def _detect_mime_type(content: bytes) -> str:
    """
    Detect MIME type using libmagic (python-magic) if available.
    Falls back to magic-byte inspection (pure Python) if not installed.
    """
    try:
        import magic
        detected = magic.from_buffer(content, mime=True)
        if detected == "image/jpg":
            return "image/jpeg"
        return detected
    except ImportError:
        pass

    # Fallback: pure-Python magic-byte inspection
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"%PDF"):
        return "application/pdf"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"
    if content.startswith(b"\x00\x00\x01\x00"):  # ICO
        return "image/x-icon"
    # No magic bytes matched
    return "application/octet-stream"


def _document_payload(doc: Document) -> dict:
    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "file_url": doc.file_url,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "file_checksum": doc.file_checksum,
        "duplicate_of_document_id": doc.duplicate_of_document_id,
        "processing_attempts": doc.processing_attempts,
        "processing_started_at": doc.processing_started_at,
        "processed_at": doc.processed_at,
        "processing_error": doc.processing_error,
        "ocr_raw_text": doc.ocr_raw_text,
        "ocr_confidence": doc.ocr_confidence,
        "ocr_provider": doc.ocr_provider,
        "ocr_engine_version": doc.ocr_engine_version,
        "ocr_duration_ms": doc.ocr_duration_ms,
        "ocr_page_count": doc.ocr_page_count,
        "ocr_language": doc.ocr_language,
        "ocr_warnings": doc.ocr_warnings,
        "ocr_pages": doc.ocr_pages,
        "extraction_confidence": doc.extraction_confidence,
        "extracted_data": doc.extracted_data,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def _document_list_item(doc: Document) -> dict:
    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "processing_attempts": doc.processing_attempts,
        "processed_at": doc.processed_at,
        "processing_error": doc.processing_error,
        "created_at": doc.created_at,
    }
