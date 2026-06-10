from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.config import get_settings
from app.core.security import hash_password
from app.api.routes import auth, companies, documents, invoices, reports
from app.models import Company, User, UserRole

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting VN Accounting API", env=settings.app_env)
    if settings.seed_demo_data and not settings.is_production:
        await seed_demo_data()
    yield
    logger.info("Shutting down VN Accounting API")


async def seed_demo_data():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "demo@vnaccounting.local"))
        if result.scalar_one_or_none():
            return

        company = Company(
            name="Cong ty TNHH Demo Viet Nam",
            tax_code="0101243150",
            address="Quan 1, TP Ho Chi Minh",
            accounting_standard="TT200",
        )
        db.add(company)
        await db.flush()

        user = User(
            email="demo@vnaccounting.local",
            hashed_password=hash_password("demo123456"),
            full_name="Demo Accountant",
            role=UserRole.ADMIN,
            company_id=company.id,
        )
        db.add(user)
        await db.commit()


app = FastAPI(
    title="VN Accounting Compliance API",
    description="Backend for Vietnam accounting and tax compliance platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
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
