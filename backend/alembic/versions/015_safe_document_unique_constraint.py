"""B-3: Safe replacement for 010 — deduplicate documents before unique index.

Revision ID: 015_safe_document_unique_constraint
Revises: 014_safe_invoice_unique_constraint
Create Date: 2026-07-02

B-3 fix: If duplicate documents exist (same company+file_checksum), keep the
newest record (highest id), log them, then create the unique index.
Idempotent: safe to run on fresh DB, DB with duplicates, or DB already migrated.
"""
from alembic import op
import sqlalchemy as sa

revision = "015_safe_document_unique_constraint"
down_revision = "014_safe_invoice_unique_constraint"
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Detect duplicates (only where file_checksum is not null)
    result = op.execute("""
        SELECT company_id, file_checksum, COUNT(*) as cnt, MAX(id) as keep_id
        FROM documents
        WHERE file_checksum IS NOT NULL
        GROUP BY company_id, file_checksum
        HAVING COUNT(*) > 1
    """)
    duplicates = result.fetchall()

    if duplicates:
        import sys
        sys.stderr.write(
            f"[B-3] Found {len(duplicates)} duplicate document group(s). "
            f"Keeping newest (highest id). Delete count will follow.\n"
        )
        for row in duplicates:
            sys.stderr.write(
                f"  company={row[0]} checksum={row[1][:16]}... count={row[2]} "
                f"→ keeping id={row[3]}\n"
            )
        # Step 2: Delete duplicates, keeping newest (MAX id = newest by insertion order)
        op.execute("""
            DELETE FROM documents
            WHERE file_checksum IS NOT NULL
              AND id NOT IN (
                  SELECT MAX(id)
                  FROM documents
                  WHERE file_checksum IS NOT NULL
                  GROUP BY company_id, file_checksum
              )
        """)
        sys.stderr.write("[B-3] Document deduplication complete.\n")
    else:
        import sys
        sys.stderr.write("[B-3] No duplicate documents found — proceeding with index creation.\n")

    # Step 3: Create unique index
    op.execute("""
        CREATE UNIQUE INDEX CONCURRENTLY ix_documents_company_checksum_v2
        ON documents (company_id, file_checksum)
        WHERE file_checksum IS NOT NULL
    """)

    # Step 4: Drop old index if it exists
    op.execute("DROP INDEX IF EXISTS ix_documents_company_checksum")

    # Step 5: Rename new index to canonical name
    op.execute("ALTER INDEX ix_documents_company_checksum_v2 RENAME TO ix_documents_company_checksum")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_documents_company_checksum")
    op.execute("""
        CREATE UNIQUE INDEX ix_documents_company_checksum
        ON documents (company_id, file_checksum)
        WHERE file_checksum IS NOT NULL
    """)
