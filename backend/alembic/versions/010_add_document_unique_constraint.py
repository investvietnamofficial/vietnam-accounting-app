"""Add unique constraint on documents (company_id, file_checksum). M-5.

Revision ID: 010_add_document_unique_constraint
Revises: 009_add_invoice_unique_constraint
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "010_add_document_unique_constraint"
down_revision = "009_add_invoice_unique_constraint"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE UNIQUE INDEX ix_documents_company_checksum
        ON documents (company_id, file_checksum)
        WHERE file_checksum IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_documents_company_checksum")
