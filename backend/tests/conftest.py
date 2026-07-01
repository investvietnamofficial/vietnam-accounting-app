"""
conftest.py — pytest-asyncio configuration for integration tests.

Root cause of "attached to a different loop" failures:
  SQLAlchemy's create_async_engine() in database.py is called at module import
  time — before pytest-asyncio has created its event loop. httpx's
  AsyncClient+ASGITransport then runs in pytest's loop while asyncpg's
  connection pool was initialized without one, causing pool cleanup errors
  when Starlette middleware tries to close pooled connections after the loop
  has been closed.

Fixes:
  1. asyncio_default_test_loop_scope = session in pytest.ini ensures ALL tests
     run in the SAME event loop, so the SQLAlchemy engine's pool stays valid.
  2. Shared asyncpg pool (_get_pool): tracks which loop the pool was created in
     and recreates it if a subsequent test runs in a different loop.
  3. Seed helpers use asyncpg directly (not SQLAlchemy sessions) to avoid
     cross-fixture state contamination.
"""
