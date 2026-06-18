"""Add extraction_confidence to invoices for report quality checks."""

from alembic import op
import sqlalchemy as sa


revision = "004_add_invoice_extraction_confidence"
down_revision = "003_add_company_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("extraction_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "extraction_confidence")
