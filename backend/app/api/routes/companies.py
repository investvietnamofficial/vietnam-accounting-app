"""Company management routes."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models import Company

router = APIRouter()

@router.get("/me")
async def get_my_company(current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TODO (Codex): Return full company profile with settings."""
    if not current_user.company_id:
        return {"company_id": None}
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    return company or {"company_id": current_user.company_id}

@router.patch("/me")
async def update_company(payload: dict, current_user=Depends(require_roles("admin")), db: AsyncSession = Depends(get_db)):
    """TODO (Codex): Update company settings — accounting standard, VAT period, etc."""
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one_or_none()
    if not company:
        return {"company_id": None}
    for field in ("name", "tax_code", "address", "phone", "email", "accounting_standard", "vat_declaration_period"):
        if field in payload:
            setattr(company, field, payload[field])
    await db.commit()
    return company
