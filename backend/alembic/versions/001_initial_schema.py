"""Initial schema for VN Accounting models."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


user_role_enum = postgresql.ENUM("admin", "accountant", "viewer", name="userrole", create_type=False)
document_status_enum = postgresql.ENUM(
    "pending",
    "processing",
    "extracted",
    "verified",
    "rejected",
    name="documentstatus",
    create_type=False,
)
document_type_enum = postgresql.ENUM(
    "invoice_vat",
    "invoice_sale",
    "receipt",
    "contract",
    "bank_statement",
    "other",
    name="documenttype",
    create_type=False,
)
vat_rate_enum = postgresql.ENUM("0", "5", "8", "10", "exempt", "na", name="vatrate", create_type=False)
journal_entry_status_enum = postgresql.ENUM(
    "draft", "posted", "reversed", name="journalentrystatus", create_type=False
)
tax_declaration_period_enum = postgresql.ENUM(
    "monthly", "quarterly", name="taxdeclarationperiod", create_type=False
)


def upgrade() -> None:
    """Create all tables, enums and indexes explicitly."""
    bind = op.get_bind()
    for enum_type in (
        user_role_enum,
        document_status_enum,
        document_type_enum,
        vat_rate_enum,
        journal_entry_status_enum,
        tax_declaration_period_enum,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("name_en", sa.String(length=500), nullable=True),
        sa.Column("tax_code", sa.String(length=20), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("accounting_standard", sa.String(length=10), nullable=False),
        sa.Column("vat_declaration_period", tax_declaration_period_enum, nullable=False),
        sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_tax_code", "companies", ["tax_code"], unique=True)

    op.create_table(
        "chart_of_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("account_code", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=500), nullable=False),
        sa.Column("account_name_en", sa.String(length=500), nullable=True),
        sa.Column("parent_code", sa.String(length=20), nullable=True),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "account_code", name="uq_chart_of_accounts_company_id_account_code"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("doc_type", document_type_enum, nullable=False),
        sa.Column("status", document_status_enum, nullable=False),
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("celery_job_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_series", sa.String(length=20), nullable=True),
        sa.Column("invoice_number", sa.String(length=50), nullable=True),
        sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invoice_type", document_type_enum, nullable=False),
        sa.Column("seller_name", sa.String(length=500), nullable=True),
        sa.Column("seller_tax_code", sa.String(length=20), nullable=True),
        sa.Column("seller_address", sa.Text(), nullable=True),
        sa.Column("seller_bank_account", sa.String(length=50), nullable=True),
        sa.Column("buyer_name", sa.String(length=500), nullable=True),
        sa.Column("buyer_tax_code", sa.String(length=20), nullable=True),
        sa.Column("buyer_address", sa.Text(), nullable=True),
        sa.Column("subtotal_amount", sa.BigInteger(), nullable=False),
        sa.Column("vat_rate", vat_rate_enum, nullable=False),
        sa.Column("vat_amount", sa.BigInteger(), nullable=False),
        sa.Column("total_amount", sa.BigInteger(), nullable=False),
        sa.Column("einvoice_code", sa.String(length=100), nullable=True),
        sa.Column("einvoice_verified", sa.Boolean(), nullable=False),
        sa.Column("einvoice_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("line_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_invoices_document_id"),
    )

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=True),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", journal_entry_status_enum, nullable=False),
        sa.Column("total_amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "journal_entry_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("journal_entry_id", sa.String(length=36), nullable=False),
        sa.Column("debit_account_code", sa.String(length=20), nullable=True),
        sa.Column("credit_account_code", sa.String(length=20), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all schema objects created by this migration."""
    bind = op.get_bind()

    op.drop_table("journal_entry_lines")
    op.drop_table("journal_entries")
    op.drop_table("invoices")
    op.drop_table("documents")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("chart_of_accounts")
    op.drop_index("ix_companies_tax_code", table_name="companies")
    op.drop_table("companies")

    for enum_type in (
        tax_declaration_period_enum,
        journal_entry_status_enum,
        vat_rate_enum,
        document_type_enum,
        document_status_enum,
        user_role_enum,
    ):
        enum_type.drop(bind, checkfirst=True)
