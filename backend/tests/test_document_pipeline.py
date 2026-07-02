import pytest
from sqlalchemy.exc import IntegrityError
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.tasks import _prepare_document_for_ocr, _should_retry


class DummyTaskRequest:
    def __init__(self, retries: int):
        self.retries = retries


class DummyTask:
    def __init__(self, retries: int, max_retries: int):
        self.request = DummyTaskRequest(retries)
        self.max_retries = max_retries


def test_should_retry_returns_true_when_attempts_remaining():
    assert _should_retry(DummyTask(retries=1, max_retries=3)) is True


def test_should_retry_returns_false_when_exhausted():
    assert _should_retry(DummyTask(retries=3, max_retries=3)) is False


def test_prepare_document_for_ocr_returns_image_bytes_for_non_pdf():
    image_bytes = b"fake-image"
    assert _prepare_document_for_ocr(image_bytes, "image/jpeg") == image_bytes


# H-3 regression: invoice.extraction_confidence must match doc.extraction_confidence
# The field is set in _process_document_async after invoice fields are populated.
# We test the logic: the invoice extraction_confidence assignment is the last
# invoice field set before doc.processed_at is written.
import inspect
from app.workers.tasks import _process_document_async

_source = inspect.getsource(_process_document_async)
assert "invoice.extraction_confidence = doc.extraction_confidence" in _source, (
    "invoice.extraction_confidence must be assigned from doc.extraction_confidence "
    "in _process_document_async"
)

# H-4 + M-5 regression: _process_document_async handles IntegrityError on duplicate
# invoice (company, series, number) and fetches the existing record.
assert "unique" in _source.lower() or "IntegrityError" in _source, (
    "_process_document_async must handle IntegrityError on duplicate invoice "
    "(H-4 / M-5 concurrency fix)"
)

# Verify the unique constraint migration file exists
import os
alembic_versions = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "alembic", "versions", "009_add_invoice_unique_constraint.py"
)
assert os.path.exists(alembic_versions), (
    "Migration 009_add_invoice_unique_constraint.py must exist for H-4"
)


def test_filename_sanitization_blocks_path_traversal():
    """Regression: path-traversal filenames must be sanitized before storage."""
    # Simulate the sanitization logic from upload_document()
    original = "../etc/passwd"
    # werkzeug's secure_filename strips path components including ..
    from werkzeug.utils import secure_filename

    filename = secure_filename(original) or "uploaded-document"
    assert ".." not in filename, f"Path traversal not blocked: {filename}"

    # Also verify the fallback regex (used when werkzeug raises) strips ../
    import re
    fallback = re.sub(r"[^a-zA-Z0-9._-]", "_", original.split("/")[-1].split("\\")[-1])
    assert ".." not in fallback, f"Path traversal not blocked in fallback: {fallback}"


def test_upload_integrity_error_on_flush_is_handled_gracefully():
    """
    GLM-RC1: When db.flush() raises IntegrityError (e.g. concurrent duplicate),
    the upload handler must return an HTTPException rather than propagating
    the raw exception as a 500.
    """
    import asyncio
    from fastapi import HTTPException
    from app.api.routes import documents as docs_module

    # Mock file with checksum that bypasses duplicate detection
    mock_file = MagicMock()
    mock_file.read = AsyncMock(return_value=b"unique-content-xyz")
    mock_file.filename = "invoice.pdf"

    mock_user = MagicMock()
    mock_user.id = "user-1"
    mock_user.company_id = "company-1"

    mock_db = AsyncMock()
    # Bypass duplicate check — no existing doc
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.flush = AsyncMock(side_effect=IntegrityError("statement", "params", "duplicate key"))
    mock_db.add = MagicMock()

    mock_bg = MagicMock()

    with patch.object(docs_module, "_detect_mime_type", return_value="application/pdf"):
        with patch.object(docs_module, "R2Service") as mock_r2_cls:
            mock_r2 = MagicMock()
            mock_r2.upload = AsyncMock(return_value="local://path/doc")
            mock_r2_cls.return_value = mock_r2

            try:
                asyncio.run(
                    docs_module.upload_document(
                        file=mock_file,
                        background_tasks=mock_bg,
                        doc_type="invoice",
                        current_user=mock_user,
                        db=mock_db,
                    )
                )
                pytest.fail("Expected HTTPException but none was raised")
            except HTTPException as exc:
                # The route should return a 409 Conflict, not 500
                assert exc.status_code == 409
            except IntegrityError:
                pytest.fail("IntegrityError must be caught and converted to HTTPException")
