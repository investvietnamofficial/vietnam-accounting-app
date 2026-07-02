"""Add invoice_direction, direction_status, direction_confidence (H-5).

Revision ID: 012_add_invoice_direction_fields
Revises: 011_add_currency_conversion_fields
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "012_add_invoice_direction_fields"
down_revision = "011_add_currency_conversion_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("invoice_direction", sa.String(20), nullable=True))
    op.add_column(
        "invoices",
        sa.Column("direction_status", sa.String(20), nullable=False, server_default="unknown"),
    )
    op.add_column("invoices", sa.Column("direction_confidence", sa.Numeric(3, 2), nullable=True))


def downgrade():
    op.drop_column("invoices", "direction_confidence")
    op.drop_column("invoices", "direction_status")
    op.drop_column("invoices", "invoice_direction")
