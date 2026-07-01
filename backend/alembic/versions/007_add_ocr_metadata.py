"""Add OCR metadata columns for production observability.

Revision ID: 007_add_ocr_metadata
Revises: 006_fix_alembic_version_coltype
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "007_add_ocr_metadata"
down_revision = "006_fix_alembic_version_coltype"
branch_labels = None
depends_on = None


def upgrade():
    # OCR provider identifier (google / paddle / mock)
    op.add_column(
        "documents",
        sa.Column("ocr_provider", sa.String(50), nullable=True),
    )
    # Engine version string for auditability
    op.add_column(
        "documents",
        sa.Column("ocr_engine_version", sa.String(50), nullable=True),
    )
    # Wall-clock time in milliseconds
    op.add_column(
        "documents",
        sa.Column("ocr_duration_ms", sa.Integer(), nullable=True),
    )
    # Number of pages successfully processed
    op.add_column(
        "documents",
        sa.Column("ocr_page_count", sa.Integer(), nullable=True),
    )
    # Language hints passed to the OCR engine
    op.add_column(
        "documents",
        sa.Column("ocr_language", sa.String(20), nullable=True),
    )
    # Non-fatal warnings (e.g. page N timed out, partial failure)
    op.add_column(
        "documents",
        sa.Column("ocr_warnings", JSONB, nullable=True),
    )
    # Per-page breakdown: [{"page_number": 1, "text": "...", "confidence": 0.92}, ...]
    op.add_column(
        "documents",
        sa.Column("ocr_pages", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("documents", "ocr_pages")
    op.drop_column("documents", "ocr_warnings")
    op.drop_column("documents", "ocr_language")
    op.drop_column("documents", "ocr_page_count")
    op.drop_column("documents", "ocr_duration_ms")
    op.drop_column("documents", "ocr_engine_version")
    op.drop_column("documents", "ocr_provider")
