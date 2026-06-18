"""Add company settings: VAS/IFRS standard, monthly/quarterly VAT period."""

from alembic import op
import sqlalchemy as sa


revision = "003_add_company_settings"
down_revision = "002_document_pipeline_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalize existing "TT200" values to "VAS" and update column default
    op.execute("UPDATE companies SET accounting_standard = 'VAS' WHERE accounting_standard = 'TT200'")
    op.alter_column("companies", "accounting_standard", server_default="VAS")


def downgrade() -> None:
    op.alter_column("companies", "accounting_standard", server_default=None)
    op.execute("UPDATE companies SET accounting_standard = 'TT200' WHERE accounting_standard = 'VAS'")
