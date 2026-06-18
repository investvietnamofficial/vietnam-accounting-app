"""Company management routes."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models import Company


router = APIRouter()


class CompanySettingsUpdate(BaseModel):
    """Only whitelisted fields can be updated; reject anything else."""

    company_name: str | None = Field(None, min_length=2, max_length=500)
    tax_code: str | None = Field(None, min_length=10, max_length=20)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=255)
    accounting_standard: Literal["VAS", "IFRS"] | None = None
    vat_period: Literal["monthly", "quarterly"] | None = None

    model_config = {"extra": "forbid"}


class CompanySettingsResponse(BaseModel):
    id: str
    name: str
    tax_code: str
    address: str | None
    phone: str | None
    email: str | None
    accounting_standard: str
    vat_declaration_period: str
    fiscal_year_start_month: int
    is_active: bool

    model_config = {"from_attributes": True}


def _company_response(company: Company) -> CompanySettingsResponse:
    return CompanySettingsResponse(
        id=company.id,
        name=company.name,
        tax_code=company.tax_code,
        address=company.address,
        phone=company.phone,
        email=company.email,
        accounting_standard=company.accounting_standard,
        vat_declaration_period=company.vat_declaration_period.value,
        fiscal_year_start_month=company.fiscal_year_start_month,
        is_active=company.is_active,
    )


@router.get("/me", response_model=CompanySettingsResponse)
async def get_my_company(
    current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Return full company profile with current settings."""
    if not current_user.company_id:
        raise HTTPException(status_code=404, detail="No company associated with this user")
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_response(company)


@router.patch("/me", response_model=CompanySettingsResponse)
async def update_company(
    payload: CompanySettingsUpdate,
    current_user=Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update company settings — accounting standard, VAT period, and profile fields."""
    if not current_user.company_id:
        raise HTTPException(status_code=404, detail="No company associated with this user")

    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update = payload.model_dump(exclude_unset=True)

    # Map camelCase keys to model fields
    if "company_name" in update:
        company.name = update.pop("company_name")
    if "vat_period" in update:
        from app.models import TaxDeclarationPeriod
        val = update.pop("vat_period")
        if val:
            company.vat_declaration_period = TaxDeclarationPeriod(val)

    # Apply remaining fields directly
    for field in ("tax_code", "address", "phone", "email", "accounting_standard"):
        if field in update and update[field] is not None:
            setattr(company, field, update[field])

    await db.commit()
    await db.refresh(company)
    return _company_response(company)
