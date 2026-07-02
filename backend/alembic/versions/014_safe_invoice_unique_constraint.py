"""B-3: Safe replacement for 009 — deduplicate invoices before unique index.

Revision ID: 014_safe_invoice_unique_constraint
Revises: 013_add_einvoice_verification_data
Create Date: 2026-07-02

B-3 fix: If duplicates exist (same company+series+number), keep the newest
record (highest id), log them, then create the unique index.
Idempotent: safe to run on fresh DB, DB with duplicates, or DB already migrated.
"""
from alembic import op
import sqlalchemy as sa

revision = "014_safe_invoice_unique_constraint"
down_revision = "013_add_einvoice_verification_data"
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Detect duplicates
    result = op.execute("""
        SELECT company_id, invoice_series, invoice_number, COUNT(*) as cnt, MAX(id) as keep_id
        FROM invoices
        WHERE invoice_series IS NOT NULL AND invoice_number IS NOT NULL
        GROUP BY company_id, invoice_series, invoice_number
        HAVING COUNT(*) > 1
    """)
    duplicates = result.fetchall()

    if duplicates:
        # Log to postgres notice (visible in docker logs via stderr)
        import sys
        sys.stderr.write(
            f"[B-3] Found {len(duplicates)} duplicate invoice group(s). "
            f"Keeping newest (highest id). Delete count will follow.\n"
        )
        for row in duplicates:
            sys.stderr.write(
                f"  company={row[0]} series={row[1]} number={row[2]} count={row[3]} "
                f"→ keeping id={row[4]}\n"
            )
        # Step 2: Delete duplicates, keeping newest (MAX id = newest by insertion order)
        # Subquery: find MAX(id) per group, delete everything else
        op.execute("""
            DELETE FROM invoices
            WHERE invoice_series IS NOT NULL
              AND invoice_number IS NOT NULL
              AND id NOT IN (
                  SELECT MAX(id)
                  FROM invoices
                  WHERE invoice_series IS NOT NULL AND invoice_number IS NOT NULL
                  GROUP BY company_id, invoice_series, invoice_number
              )
        """)
        sys.stderr.write("[B-3] Deduplication complete.\n")
    else:
        import sys
        sys.stderr.write("[B-3] No duplicate invoices found — proceeding with index creation.\n")

    # Step 3: Create unique index (only succeeds if no duplicates remain)
    # Use CONCURRENTLY to avoid locking reads/writes during creation
    op.execute("""
        CREATE UNIQUE INDEX CONCURRENTLY ix_invoices_company_series_number_v2
        ON invoices (company_id, invoice_series, invoice_number)
        WHERE invoice_series IS NOT NULL AND invoice_number IS NOT NULL
    """)

    # Step 4: Drop old index if it exists (from failed 009 or previous attempt)
    op.execute("DROP INDEX IF EXISTS ix_invoices_company_series_number")

    # Step 5: Rename new index to canonical name
    op.execute("ALTER INDEX ix_invoices_company_series_number_v2 RENAME TO ix_invoices_company_series_number")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_invoices_company_series_number")
    op.execute("""
        CREATE UNIQUE INDEX ix_invoices_company_series_number
        ON invoices (company_id, invoice_series, invoice_number)
        WHERE invoice_series IS NOT NULL AND invoice_number IS NOT NULL
    """)
