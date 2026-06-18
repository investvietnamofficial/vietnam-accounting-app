from contextlib import asynccontextmanager
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.core.config import get_settings
from app.api.routes import auth, companies, documents, invoices, reports

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
