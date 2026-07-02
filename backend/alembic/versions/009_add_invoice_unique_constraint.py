"""Add unique constraint on invoices (company_id, invoice_series, invoice_number).

Revision ID: 009_add_invoice_unique_constraint
Revises: 008_add_currency_and_tenant_constraint
Create Date: 2026-07-02

H-4: Prevent duplicate invoices from being stored. The partial unique index
only applies when both invoice_series and invoice_number are non-null, which
covers the common case of formal invoices. Invoices uploaded without a
readable series/number are excluded from the constraint.
"""

from alembic import op
import sqlalchemy as sa

revision = "009_add_invoice_unique_constraint"
down_revision = "008_add_currency_and_tenant_constraint"
branch_labels = None
depends_on = None


def upgrade():
    # Partial unique index — only enforced when both fields are present.
    # Allows: same series+number across different companies (different tenant).
    # Prevents: same company uploading the same invoice twice.
    op.execute("""
        CREATE UNIQUE INDEX ix_invoices_company_series_number
        ON invoices (company_id, invoice_series, invoice_number)
        WHERE invoice_series IS NOT NULL AND invoice_number IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_invoices_company_series_number")
