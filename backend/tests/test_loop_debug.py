"""Debug test: mirror the exact integration test structure."""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import create_access_token, create_refresh_token


# Pre-computed bcrypt hash of "TestPass123!"
_TEST_HASH = "$2b$12$Sj9UWkZ7NF8Ulb8i5I6xMucGnSBdaUuoQipsbudZxeJwYTF0kcN.S"

_DB_URL = None

def _db_url():
    global _DB_URL
    if _DB_URL is None:
        from app.core.config import get_settings
        url = get_settings().database_url
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
        _DB_URL = url
    return _DB_URL


import asyncpg
_PG_POOL = None
_PG_POOL_LOOP = None


async def _get_pool():
    global _PG_POOL, _PG_POOL_LOOP
    current_loop = asyncio.get_running_loop()
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
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO companies (id, name, tax_code, accounting_standard, vat_declaration_period, fiscal_year_start_month, is_active) "
            "VALUES ($1, $2, $3, 'VAS', 'quarterly', 1, true) "
            "ON CONFLICT (tax_code) DO UPDATE SET name = EXCLUDED.name",
            company_id, name, tax_code
        )
    return company_id


async def seed_user(user_id: str, email: str, company_id: str, active: bool = True) -> str:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, hashed_password, full_name, company_id, is_active, role) "
            "VALUES ($1, $2, $3, 'Test User', $4, $5, 'accountant') "
            "ON CONFLICT (id) DO UPDATE SET is_active = EXCLUDED.is_active",
            user_id, email, _TEST_HASH, company_id, active
        )
    return user_id


def auth_header(user_id: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.mark.asyncio
async def test_login_active_user():
    """Mirrors test_login_requires_active_user."""
    await seed_company("co-debug1", "7777111111")
    await seed_user("user-debug1", "debug1@test.com", "co-debug1", active=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=15) as client:
        resp = await client.post(
            "/api/v1/auth/token",
            data={"username": "debug1@test.com", "password": "TestPass123!"},
        )
        print(f"Login status: {resp.status_code}")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_rejects_inactive():
    """Mirrors test_refresh_token_rejects_inactive_user."""
    await seed_company("co-debug2", "7777222222")
    await seed_user("user-debug2", "debug2@test.com", "co-debug2", active=False)

    refresh = create_refresh_token("user-debug2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=15) as client:
        resp = await client.post(
            "/api/v1/auth/token/refresh",
            json={"refresh_token": refresh},
        )
        print(f"Refresh status: {resp.status_code}")
        assert resp.status_code == 401
