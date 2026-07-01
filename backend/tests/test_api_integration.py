"""
Integration tests for the FastAPI routes.
Tests auth, tenant isolation, document pipeline, and invoice list filtering.

Run with: PYTHONPATH=backend python3 -m pytest tests/test_api_integration.py -v

Event-loop fix:
  Uses starlette.testclient.TestClient (sync, runs its own loop internally) instead
  of httpx.AsyncClient + ASGITransport. This avoids asyncpg's connection pool
  "attached to a different loop" errors when pytest-asyncio manages the test loop.
- bcrypt 4.x (passlib 1.7.4 + bcrypt 5.x incompatibility breaks password verify)
- All alembic migrations applied locally (migration 008 adds currency_code + users.company_id NOT NULL)
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token, create_refresh_token
from app.models import Company, User, Document, DocumentStatus, DocumentType, Invoice, VATRate

# Pre-computed bcrypt hash of "TestPass123!" — avoids bcrypt init cost in async context.
_TEST_PASSWORD_HASH = "$2b$12$Sj9UWkZ7NF8Ulb8i5I6xMucGnSBdaUuoQipsbudZxeJwYTF0kcN.S"


# ---------------------------------------------------------------------------
# Helpers — use asyncpg directly to avoid SQLAlchemy pool event-loop issues
# ---------------------------------------------------------------------------

import uuid

def auth_header(user_id: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _db_url() -> str:
    """Strip asyncpg driver prefix so asyncpg.connect() accepts the URL."""
    from app.core.config import get_settings
    url = get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


# Shared module-level pool — initialized lazily on first seed call.
# asyncpg pools are bound to the event loop they were created in.
# If a subsequent test runs in a DIFFERENT loop, we close the old pool
# and create a fresh one in the current loop.
import asyncio
_PG_POOL: "asyncpg.Pool | None" = None
_PG_POOL_LOOP: "asyncio.AbstractEventLoop | None" = None


async def _get_pool() -> "asyncpg.Pool":
    """Get (or create) a connection pool in the CURRENT event loop."""
    global _PG_POOL, _PG_POOL_LOOP
    import asyncpg

    current_loop = asyncio.get_running_loop()
    # If pool was created in a different loop, close it and recreate
    if _PG_POOL is not None and _PG_POOL_LOOP is not current_loop:
        try:
            await _PG_POOL.close()
        except Exception:
            pass
        _PG_POOL = None
        _PG_POOL_LOOP = None

    if _PG_POOL is None:
        _PG_POOL = await asyncpg.create_pool(_db_url(), min_size=1, max_size=5)
        _PG_POOL_LOOP = current_loop

    return _PG_POOL


async def seed_company(company_id: str, tax_code: str, name: str = "Test Co") -> str:
    """Insert/replace a company by id. Cleans up by tax_code to handle stale rows from previous runs."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        # Cascade delete: invoices → documents → users → company (all via tax_code to catch stale rows)
        await conn.execute(
            "DELETE FROM invoices WHERE document_id IN (SELECT id FROM documents WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1))",
            tax_code
        )
        await conn.execute(
            "DELETE FROM documents WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
            tax_code
        )
        await conn.execute(
            "DELETE FROM users WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
            tax_code
        )
        await conn.execute("DELETE FROM companies WHERE tax_code = $1", tax_code)
        await conn.execute(
            "INSERT INTO companies (id, name, tax_code, accounting_standard, vat_declaration_period, fiscal_year_start_month, is_active) "
            "VALUES ($1, $2, $3, 'VAS', 'quarterly', 1, true)",
            company_id, name, tax_code
        )
    return company_id


async def seed_user(user_id: str, email: str, company_id: str, active: bool = True) -> str:
    """Insert/update a user. Returns user id."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, hashed_password, full_name, company_id, is_active, role) "
            "VALUES ($1, $2, $3, 'Test User', $4, $5, 'accountant') "
            "ON CONFLICT (id) DO UPDATE SET is_active = EXCLUDED.is_active",
            user_id, email, _TEST_PASSWORD_HASH, company_id, active
        )
    return user_id


async def seed_invoice(
    inv_id: str,
    doc_id: str,
    company_id: str,
    uploaded_by_id: str,
    seller_tax_code: str,
    *,
    subtotal: int = 10_000_000,
    vat_amount: int = 1_000_000,
    total: int = 11_000_000,
) -> None:
    """Insert document + invoice pair with ON CONFLICT DO NOTHING to handle stale test data."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO documents (id, company_id, uploaded_by_id, file_name, file_url, file_size_bytes, mime_type, doc_type, status) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, 'invoice_vat', 'extracted') "
            "ON CONFLICT (id) DO NOTHING",
            doc_id, company_id, uploaded_by_id, f"{inv_id}.pdf", f"local://{inv_id}.pdf", 1024, "application/pdf"
        )
        await conn.execute(
            "INSERT INTO invoices (id, company_id, document_id, invoice_series, invoice_number, seller_tax_code, subtotal_amount, vat_rate, vat_amount, total_amount, invoice_type, currency_code) "
            "VALUES ($1, $2, $3, 'TT/26E', $4, $5, $6, '10', $7, $8, 'invoice_vat', 'VND') "
            "ON CONFLICT (id) DO NOTHING",
            inv_id, company_id, doc_id, inv_id[-3:], seller_tax_code, subtotal, vat_amount, total
        )


# ---------------------------------------------------------------------------
# Auth Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_requires_active_user():
    """Login with an inactive user returns 403."""
    await seed_company("co-inactive", "7777777777")
    await seed_user("user-inactive", "inactive@test.com", "co-inactive", active=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/token",
            data={"username": "inactive@test.com", "password": "TestPass123!"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token_rejects_inactive_user():
    """A refresh token for a deactivated user cannot mint a new access token."""
    await seed_company("co-rt-inactive", "8888888888")
    await seed_user("user-rt-inactive", "rt-inactive@test.com", "co-rt-inactive", active=False)

    refresh = create_refresh_token("user-rt-inactive")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=15) as client:
        resp = await client.post(
            "/api/v1/auth/token/refresh",
            json={"refresh_token": refresh},
        )
        assert resp.status_code == 401
        assert "inactive" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_protected_endpoint_requires_token():
    """No token → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tenant Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_cannot_access_other_company_invoices():
    """User from Company A gets 404 when accessing Company B's invoice."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Cascade delete by tax_code to handle stale rows with same tax_code but different id
            await conn.execute(
                "DELETE FROM documents WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
                "1111111111"
            )
            await conn.execute(
                "DELETE FROM users WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
                "1111111111"
            )
            await conn.execute("DELETE FROM companies WHERE tax_code = $1", "1111111111")
            await conn.execute(
                "INSERT INTO companies (id, name, tax_code, accounting_standard, vat_declaration_period, fiscal_year_start_month, is_active) "
                "VALUES ($1, $2, $3, 'VAS', 'quarterly', 1, true)",
                "co-iso-a", "Company A", "1111111111"
            )
            await conn.execute(
                "INSERT INTO users (id, email, hashed_password, full_name, company_id, is_active, role) "
                "VALUES ($1, $2, $3, 'User A', $4, true, 'accountant') "
                "ON CONFLICT (id) DO UPDATE SET is_active = EXCLUDED.is_active",
                "user-iso-a", "iso-a@test.com", _TEST_PASSWORD_HASH, "co-iso-a"
            )
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM invoices WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
                "2222222222"
            )
            await conn.execute(
                "DELETE FROM documents WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
                "2222222222"
            )
            await conn.execute(
                "DELETE FROM users WHERE company_id IN (SELECT id FROM companies WHERE tax_code = $1)",
                "2222222222"
            )
            await conn.execute("DELETE FROM companies WHERE tax_code = $1", "2222222222")
            await conn.execute(
                "INSERT INTO companies (id, name, tax_code, accounting_standard, vat_declaration_period, fiscal_year_start_month, is_active) "
                "VALUES ($1, $2, $3, 'VAS', 'quarterly', 1, true)",
                "co-iso-b", "Company B", "2222222222"
            )
            await conn.execute(
                "INSERT INTO users (id, email, hashed_password, full_name, company_id, is_active, role) "
                "VALUES ($1, $2, $3, 'User B', $4, true, 'accountant') "
                "ON CONFLICT (id) DO UPDATE SET is_active = EXCLUDED.is_active",
                "user-iso-b", "iso-b@test.com", _TEST_PASSWORD_HASH, "co-iso-b"
            )
            await conn.execute(
                "INSERT INTO documents (id, company_id, uploaded_by_id, file_name, file_url, file_size_bytes, mime_type, doc_type, status) "
                "VALUES ($1, $2, $3, $4, $5, 1024, 'application/pdf', 'invoice_vat', 'extracted') "
                "ON CONFLICT (id) DO NOTHING",
                "doc-iso-b", "co-iso-b", "user-iso-b", "inv-iso-b.pdf", "local://inv-iso-b.pdf"
            )
            await conn.execute(
                "INSERT INTO invoices (id, company_id, document_id, invoice_series, invoice_number, seller_tax_code, subtotal_amount, vat_rate, vat_amount, total_amount, invoice_type, currency_code) "
                "VALUES ($1, $2, $3, 'TT/26E', 'B01', $4, 10000000, '10', 1000000, 11000000, 'invoice_vat', 'VND') "
                "ON CONFLICT (id) DO NOTHING",
                "inv-iso-b", "co-iso-b", "doc-iso-b", "2222222222"
            )

    # User A tries to access User B's invoice → should be 404
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=15) as client:
        resp = await client.get("/api/v1/invoices/inv-iso-b", headers=auth_header("user-iso-a"))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Invoice List Pagination (F-004, F-005)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invoice_type_filter_returns_correct_total():
    """Filtering by invoice_type returns the correct total count (not len of page)."""
    await seed_company("co-pag", "3333333333")
    await seed_user("user-pag", "pag@test.com", "co-pag")
    # inv-pag-0: sale (seller = company tax_code)
    await seed_invoice("inv-pag-0", "doc-pag-0", "co-pag", "user-pag", "3333333333")
    # inv-pag-1: sale
    await seed_invoice("inv-pag-1", "doc-pag-1", "co-pag", "user-pag", "3333333333")
    # inv-pag-2: purchase (different seller)
    await seed_invoice("inv-pag-2", "doc-pag-2", "co-pag", "user-pag", "4444444444")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=15) as client:
        # Filter sales → 2
        resp = await client.get("/api/v1/invoices/", params={"invoice_type": "sales"}, headers=auth_header("user-pag"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2, f"sales: expected 2, got {data['total']}"
        assert len(data["items"]) == 2

        # Filter purchases → 1
        resp = await client.get("/api/v1/invoices/", params={"invoice_type": "purchase"}, headers=auth_header("user-pag"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1, f"purchase: expected 1, got {data['total']}"


# ---------------------------------------------------------------------------
# File Upload Security (F-040, F-041)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsupported_mime_returns_415():
    """Upload with unsupported MIME type returns 415."""
    await seed_company("co-upload", "5555555555")
    await seed_user("user-upload", "upload@test.com", "co-upload")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=15) as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            headers=auth_header("user-upload"),
            files={"file": ("test.exe", b"MZ...", "application/x-msdownload")},
            data={"doc_type": "invoice"},
        )
        assert resp.status_code == 415


def test_magic_byte_fallback_works():
    """Magic-byte fallback correctly identifies PNG/JPEG/PDF when python-magic is absent."""
    import sys
    import importlib

    # Save and remove magic from sys.modules so re-import triggers fresh import
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "magic" or k.startswith("magic.")}
    try:
        # Patch importlib.__import__ so that importing 'magic' raises ImportError
        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
        def blocking_import(name, *args, **kwargs):
            if name == "magic" or name.startswith("magic."):
                raise ImportError("magic unavailable")
            return original_import(name, *args, **kwargs)

        __builtins__["__import__"] = blocking_import if isinstance(__builtins__, dict) else blocking_import

        # Drop any cached _detect_mime_type so we get the fresh import
        sys.modules.pop("app.api.routes.documents", None)
        from app.api.routes.documents import _detect_mime_type

        assert _detect_mime_type(b"\xff\xd8\xff\xe0test") == "image/jpeg"
        assert _detect_mime_type(b"%PDF-1.4 test") == "application/pdf"
        # PNG: \x89 P N G \r \n \x1a \n
        assert _detect_mime_type(b"\x89PNG\r\n\x1a\ntest") == "image/png"
        assert _detect_mime_type(b"RIFF\x0c\x00\x00\x00WEBP") == "image/webp"
        assert _detect_mime_type(b"GIF89atest") == "image/gif"
        # Unknown → application/octet-stream
        assert _detect_mime_type(b"random bytes") == "application/octet-stream"
    finally:
        __builtins__["__import__"] = original_import if isinstance(__builtins__, dict) else original_import
        sys.modules.update(saved)
        # Drop the cached _detect_mime_type to restore normal state
        sys.modules.pop("app.api.routes.documents", None)


# ---------------------------------------------------------------------------
# Extraction Validation (F-014)
# ---------------------------------------------------------------------------

def test_structural_mismatch_reduces_confidence():
    """When subtotal + vat ≠ total, confidence is reduced and note is added."""
    from app.services.extraction.claude_extractor import ExtractionService
    svc = ExtractionService()
    data = {
        "invoice_series": "AA/26E", "invoice_number": "0001", "invoice_date": "2026-01-01",
        "invoice_type": "invoice_vat", "seller_name": "Test", "seller_tax_code": "1234567890",
        "seller_address": "123 St", "buyer_name": "Buyer", "buyer_tax_code": "0987654321",
        "buyer_address": "456 Ave", "subtotal_amount": 1_000_000,
        "vat_rate": "10", "vat_amount": 100_000,
        "total_amount": 5_000_000,  # wrong! should be 1_100_000
        "line_items": [], "einvoice_code": None, "notes": None, "confidence": 0.95,
    }
    result = svc._validate_and_clean(data)
    assert result["_structural_mismatch"] is True
    assert result["confidence"] <= 0.4
    assert "Structural mismatch" in (result.get("notes") or "")


def test_implausible_amount_is_cleared():
    """Amounts > 1 trillion VND are cleared and confidence is reduced."""
    from app.services.extraction.claude_extractor import ExtractionService
    svc = ExtractionService()
    data = {
        "invoice_series": None, "invoice_number": None, "invoice_date": None,
        "invoice_type": "invoice_vat", "seller_name": None, "seller_tax_code": None,
        "seller_address": None, "buyer_name": None, "buyer_tax_code": None,
        "buyer_address": None,
        "subtotal_amount": 9_999_999_999_999,  # > 1 trillion
        "vat_rate": "10", "vat_amount": 999_999_999_999,
        "total_amount": 10_999_999_999_998,
        "line_items": [], "einvoice_code": None, "notes": None, "confidence": 0.9,
    }
    result = svc._validate_and_clean(data)
    assert result["subtotal_amount"] is None  # cleared as implausible
    assert result["confidence"] <= 0.3


# ---------------------------------------------------------------------------
# Currency Detection (F-019)
# ---------------------------------------------------------------------------

def test_foreign_currency_flags_for_review():
    """A USD invoice is flagged in the notes and confidence is reduced."""
    from app.services.extraction.claude_extractor import ExtractionService
    svc = ExtractionService()
    data = {
        "invoice_series": None, "invoice_number": None, "invoice_date": None,
        "invoice_type": "invoice_vat", "seller_name": None, "seller_tax_code": None,
        "seller_address": None, "buyer_name": None, "buyer_tax_code": None,
        "buyer_address": None,
        "subtotal_amount": 10000, "vat_rate": "10", "vat_amount": 1000,
        "total_amount": 11000, "line_items": [], "einvoice_code": None,
        "notes": None, "confidence": 0.9, "currency_code": "USD",
    }
    result = svc._validate_and_clean(data)
    assert "USD" in (result.get("notes") or "")
    assert result["confidence"] <= 0.5


# ---------------------------------------------------------------------------
# Invoice Direction (F-018)
# ---------------------------------------------------------------------------

def test_missing_seller_tax_code_returns_uncertain_direction():
    """When seller_tax_code is None, direction is flagged as uncertain."""
    from app.models import Company
    from app.api.routes.reports import _invoice_direction

    company = Company(id="co-dir", name="Dir Co", tax_code="5555555555")
    inv = Invoice(
        id="inv-dir", company_id="co-dir", document_id="doc-dir",
        seller_tax_code=None, buyer_tax_code="5555555555",
        subtotal_amount=1_000_000, vat_rate=VATRate.TEN,
        vat_amount=100_000, total_amount=1_100_000,
    )
    direction, certain = _invoice_direction(inv, company)
    assert direction == "purchase"
    assert certain is False  # uncertain because seller_tax_code is missing


# ---------------------------------------------------------------------------
# CIT Aggregation (F-022)
# ---------------------------------------------------------------------------

def test_non_deductible_6xx_accounts_excluded():
    """Accounts 661, 662, 621 etc. are NOT deductible; only 632, 635, 641, 642."""
    from app.api.routes.reports import _aggregate_cit_bases
    from app.models import JournalEntry, JournalEntryLine, JournalEntryStatus
    from datetime import datetime, UTC

    entry = JournalEntry(
        id="je-cit", company_id="co-cit",
        entry_date=datetime(2026, 3, 31, tzinfo=UTC),
        description="Mixed", status=JournalEntryStatus.POSTED, total_amount=0,
    )
    entry.lines = [
        JournalEntryLine(journal_entry_id="je-cit", debit_account_code="632", credit_account_code="156", amount=100_000_000),  # deductible
        JournalEntryLine(journal_entry_id="je-cit", debit_account_code="642", credit_account_code="334", amount=50_000_000),   # deductible
        JournalEntryLine(journal_entry_id="je-cit", debit_account_code="661", credit_account_code="111", amount=200_000_000),  # NOT deductible
        JournalEntryLine(journal_entry_id="je-cit", debit_account_code="662", credit_account_code="112", amount=75_000_000),  # NOT deductible
        JournalEntryLine(journal_entry_id="je-cit", debit_account_code="621", credit_account_code="331", amount=30_000_000),  # NOT deductible
    ]
    revenue, deductible, other_income, other_exp = _aggregate_cit_bases([entry])
    assert deductible == 150_000_000, f"Expected 150M (632+642), got {deductible}"


# ---------------------------------------------------------------------------
# Regex Amount Normalization (F-016)
# ---------------------------------------------------------------------------

def test_vietnamese_decimal_separator_truncated():
    """'1.500.000,50' → 1500000 (not 150000050)."""
    from app.services.extraction.claude_extractor import ExtractionService
    svc = ExtractionService()
    assert svc._normalize_amount_string("1.500.000,50") == 1_500_000


def test_plain_integer():
    from app.services.extraction.claude_extractor import ExtractionService
    svc = ExtractionService()
    assert svc._normalize_amount_string("1500000") == 1_500_000


def test_vietnamese_thousand_separator():
    from app.services.extraction.claude_extractor import ExtractionService
    svc = ExtractionService()
    assert svc._normalize_amount_string("1.500.000") == 1_500_000
