"""Add einvoice_verification_data to invoices (H-5).

Revision ID: 013_add_einvoice_verification_data
Revises: 012_add_invoice_direction_fields
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "013_add_einvoice_verification_data"
down_revision = "012_add_invoice_direction_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invoices",
        sa.Column("einvoice_verification_data", sa.JSON, nullable=True),
    )


def downgrade():
    op.drop_column("invoices", "einvoice_verification_data")
