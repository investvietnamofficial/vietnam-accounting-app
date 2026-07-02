from contextlib import asynccontextmanager
import uuid

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.core.config import get_settings
from app.api.routes import auth, companies, documents, invoices, reports

# ── Prometheus metrics ──────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
DOCUMENT_UPLOAD_COUNT = Counter(
    "document_uploads_total",
    "Total document uploads",
    ["status"],  # success | duplicate | error
)
OCR_PROCESSING_COUNT = Counter(
    "ocr_processing_total",
    "Total OCR processing runs",
    ["engine", "status"],  # success | error
)

settings = get_settings()

# ── Structured logging configuration ─────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()


def configure_sentry():
    """Wire Sentry if DSN is configured."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlAlchemyIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlAlchemyIntegration(),
            ],
            # Scrub tokens and passwords from events
            send_default_pii=False,
        )
        logger.info("sentry_initialized", dsn_masked="***")
    except Exception as exc:
        logger.warning("sentry_init_failed", error=str(exc))


configure_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting", env=settings.app_env, version="0.1.0")
    yield
    logger.info("app_shutting_down")


app = FastAPI(
    title="VN Accounting Compliance API",
    description="Backend for Vietnam accounting and tax compliance platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Inject request_id into every log entry."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    """Record request count and latency for Prometheus scraping."""
    import time
    if request.url.path in ("/metrics", "/health", "/healthz"):
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    method = request.method
    endpoint = request.url.path
    status = str(response.status_code)
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
    return response


# ── Global exception handler — never leak internals ───────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=str(request.url.path), exc=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/v1/companies", tags=["companies"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(invoices.router, prefix="/api/v1/invoices", tags=["invoices"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/healthz")
async def healthz():
    """
    Deep health check: verifies DB and Redis connectivity.
    Used by load balancers and orchestrators in production.
    """
    checks = {"db": "unknown", "redis": "unknown"}

    # DB check
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            checks["db"] = "ok"
    except Exception as exc:
        logger.error("healthz_db_check_failed", error=str(exc))
        checks["db"] = f"error: {exc}"

    # Redis check
    try:
        import redis.asyncio as redis

        r = redis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.warning("healthz_redis_check_failed", error=str(exc))
        checks["redis"] = f"error: {exc}"

    overall = "ok" if checks["db"] == "ok" else "degraded"
    return {
        "status": overall,
        "env": settings.app_env,
        "checks": checks,
    }


# M-6: require authentication on /debug/db
from app.api.routes.auth import get_current_user  # noqa: F401, E402


@app.get("/debug/db")
async def debug_db(current_user=Depends(get_current_user)):
    """
    TEMPORARY: returns DB state snapshot for deployment verification.
    Lists tables, Alembic version, and sample row counts.
    Only available when APP_ENV is not 'production'.
    """
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Not available in production")
    try:
        async with AsyncSessionLocal() as db:
            # List tables
            tables = await db.execute(text("""
                SELECT tablename FROM pg_tables WHERE schemaname='public'
                ORDER BY tablename
            """))
            table_list = [r[0] for r in tables.fetchall()]

            # Alembic version
            ver = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            alembic_ver = ver.scalar()

            # Row counts for core tables
            counts = {}
            for t in ["companies", "documents", "invoices", "users", "journal_entries"]:
                try:
                    r = await db.execute(text(f"SELECT count(*) FROM {t}"))
                    counts[t] = r.scalar()
                except Exception:
                    counts[t] = "table_not_found"

            return {
                "status": "ok",
                "tables": table_list,
                "alembic_version": alembic_ver,
                "row_counts": counts,
            }
    except Exception as exc:
        logger.error("debug_db_failed", error=str(exc))
        return {"status": "error", "detail": str(exc)}, 500


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics scrape endpoint.
    Collected by Prometheus server at scrape_interval.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
