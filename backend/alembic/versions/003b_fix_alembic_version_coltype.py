"""Fix alembic_version column size for long migration names."""

from alembic import op
import sqlalchemy as sa


revision = "003b_fix_alembic_version_coltype"
down_revision = "003_add_company_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("alembic_version", "version_num",
                    type_=sa.String(64), existing_type=sa.String(32),
                    existing_nullable=False)


def downgrade() -> None:
    op.alter_column("alembic_version", "version_num",
                    type_=sa.String(32), existing_type=sa.String(64),
                    existing_nullable=False)
