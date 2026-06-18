"""Add performance indexes on invoices table.

Revision ID: 003_add_indexes
Revises: 002_document_pipeline_hardening
"""
from alembic import op

revision = "003_add_indexes"
down_revision = "002_document_pipeline_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # invoice_date: primary filter for tax-report date-range queries
    op.create_index("ix_invoices_invoice_date", "invoices", ["invoice_date"], unique=False)
    # einvoice_verified: filter for unverified invoices in batch GDT checks
    op.create_index("ix_invoices_einvoice_verified", "invoices", ["einvoice_verified"], unique=False)
    # company_id: tenant isolation + invoice list filtering (already a FK, adding explicit index)
    op.create_index("ix_invoices_company_id", "invoices", ["company_id"], unique=False)
    # created_at: admin audit queries sorted by ingestion time
    op.create_index("ix_invoices_created_at", "invoices", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_invoices_created_at", table_name="invoices")
    op.drop_index("ix_invoices_company_id", table_name="invoices")
    op.drop_index("ix_invoices_einvoice_verified", table_name="invoices")
    op.drop_index("ix_invoices_invoice_date", table_name="invoices")
