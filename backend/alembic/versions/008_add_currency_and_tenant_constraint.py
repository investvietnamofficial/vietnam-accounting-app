"""Add currency_code to invoices; add company_id NOT NULL constraint.

Revision ID: 008_add_currency_and_tenant_constraint
Revises: 007_add_ocr_metadata
Create Date: 2026-07-02

Changes:
- invoices.currency_code: ISO 4217 currency code (default 'VND').
  Non-VND invoices are flagged at extraction time and must be reviewed
  before inclusion in tax filings.
- users.company_id: add NOT NULL constraint now that all users have a company.
  The nullable column was a migration artifact; every user is created with
  a company at registration time.
"""

from alembic import op
import sqlalchemy as sa

revision = "008_add_currency_and_tenant_constraint"
down_revision = "007_add_ocr_metadata"
branch_labels = None
depends_on = None


def upgrade():
    # invoices.currency_code
    op.add_column(
        "invoices",
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="VND"),
    )

    # users.company_id NOT NULL — all existing users already have a company
    # First backfill any NULL values (should be none in practice)
    op.execute("UPDATE users SET company_id = (SELECT id FROM companies WHERE name = 'Unknown') WHERE company_id IS NULL")
    op.alter_column("users", "company_id", nullable=False)


def downgrade():
    op.drop_column("invoices", "currency_code")
    op.alter_column("users", "company_id", nullable=True)
