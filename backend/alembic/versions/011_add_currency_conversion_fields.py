"""Add currency conversion fields to invoices (M-8).

Revision ID: 011_add_currency_conversion_fields
Revises: 010_add_document_unique_constraint
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "011_add_currency_conversion_fields"
down_revision = "010_add_document_unique_constraint"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("exchange_rate", sa.Numeric(12, 4), nullable=True))
    op.add_column("invoices", sa.Column("exchange_source", sa.String(50), nullable=True))
    op.add_column("invoices", sa.Column("converted_vnd_amount", sa.BigInteger, nullable=True))


def downgrade():
    op.drop_column("invoices", "converted_vnd_amount")
    op.drop_column("invoices", "exchange_source")
    op.drop_column("invoices", "exchange_rate")
