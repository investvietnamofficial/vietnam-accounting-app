"""Harden document pipeline state and duplicate tracking."""

from alembic import op
import sqlalchemy as sa


revision = "002_document_pipeline_hardening"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'failed'")
    op.add_column("documents", sa.Column("file_checksum", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("duplicate_of_document_id", sa.String(length=36), nullable=True))
    op.add_column("documents", sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.create_index("ix_documents_file_checksum", "documents", ["file_checksum"], unique=False)
    op.create_foreign_key(
        "fk_documents_duplicate_of_document_id",
        "documents",
        "documents",
        ["duplicate_of_document_id"],
        ["id"],
    )
    op.alter_column("documents", "processing_attempts", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_documents_duplicate_of_document_id", "documents", type_="foreignkey")
    op.drop_index("ix_documents_file_checksum", table_name="documents")
    op.drop_column("documents", "processing_error")
    op.drop_column("documents", "processed_at")
    op.drop_column("documents", "processing_started_at")
    op.drop_column("documents", "processing_attempts")
    op.drop_column("documents", "duplicate_of_document_id")
    op.drop_column("documents", "file_checksum")
