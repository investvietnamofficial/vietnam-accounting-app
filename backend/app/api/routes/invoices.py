"""Invoice CRUD and verification routes."""
import json
from datetime import datetime, timedelta
from typing import Literal, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Invoice, VATRate, DocumentType


router = APIRouter()


@router.get("/")
async def list_invoices(
    date_from: Annotated[str | None, Query(description="Filter invoices from this date (YYYY-MM-DD)")] = None,
    date_to: Annotated[str | None, Query(description="Filter invoices up to this date (YYYY-MM-DD)")] = None,
    vat_rate: Annotated[float | None, Query(description="VAT rate: 0.0, 0.05, 0.08, 0.10")] = None,
    seller_name: Annotated[str | None, Query(description="Seller name (partial match, case-insensitive)")] = None,
    buyer_name: Annotated[str | None, Query(description="Buyer name (partial match, case-insensitive)")] = None,
    verification_status: Annotated[Literal["pending", "verified", "failed"] | None, Query(description="Verification status")] = None,
    invoice_type: Annotated[Literal["sales", "purchase"] | None, Query(description="Invoice direction")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List invoices with optional filters for date range, VAT rate, seller/buyer name, verification status, and direction."""
    # Get company tax_code early — needed for direction filter
    from app.models import Company
    co_result = await db.execute(select(Company.tax_code).where(Company.id == current_user.company_id))
    company_tax_code = co_result.scalar_one_or_none()

    # Build direction filter in SQL (normalized seller_tax_code vs company tax_code)
    # sale = seller_tax_code matches company_tax_code; purchase = otherwise
    direction_clause = None
    if invoice_type and company_tax_code:
        # Normalize both in SQL: replace hyphens and spaces
        norm_company = func.replace(func.replace(func.replace(
            literal(company_tax_code), literal("-"), literal("")),
            literal(" "), literal("")),
            literal("\n"), literal(""))
        norm_seller = func.replace(func.replace(func.replace(
            Invoice.seller_tax_code, literal("-"), literal("")),
            literal(" "), literal("")),
            literal("\n"), literal(""))
        is_sale = norm_seller == norm_company
        direction_clause = is_sale if invoice_type == "sales" else (~is_sale)

    # Build base query with all filters
    query = select(Invoice).where(Invoice.company_id == current_user.company_id)

    # Date range filters
    if date_from:
        try:
            from_dt = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.where(Invoice.invoice_date >= from_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_from must be in YYYY-MM-DD format")
    if date_to:
        try:
            to_dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.where(Invoice.invoice_date < to_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_to must be in YYYY-MM-DD format")

    # VAT rate filter
    if vat_rate is not None:
        rate_map: dict[float, VATRate] = {0.0: VATRate.ZERO, 0.05: VATRate.FIVE, 0.08: VATRate.EIGHT, 0.10: VATRate.TEN}
        if vat_rate not in rate_map:
            raise HTTPException(status_code=400, detail="vat_rate must be one of: 0.0, 0.05, 0.08, 0.10")
        query = query.where(Invoice.vat_rate == rate_map[vat_rate])

    # Seller name (partial, case-insensitive)
    if seller_name:
        query = query.where(Invoice.seller_name.ilike(f"%{seller_name}%"))

    # Buyer name (partial, case-insensitive)
    if buyer_name:
        query = query.where(Invoice.buyer_name.ilike(f"%{buyer_name}%"))

    # Verification status
    if verification_status == "verified":
        query = query.where(Invoice.einvoice_verified == True)
    elif verification_status == "pending":
        query = query.where(or_(Invoice.einvoice_verified == False, Invoice.einvoice_verified.is_(None)))

    # Invoice direction (SQL-level — applied BEFORE pagination)
    if direction_clause is not None:
        query = query.where(direction_clause)

    # Count query — apply same filters including direction
    count_query = select(func.count()).select_from(Invoice).where(Invoice.company_id == current_user.company_id)
    if date_from:
        count_query = count_query.where(Invoice.invoice_date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        count_query = count_query.where(Invoice.invoice_date < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
    if vat_rate is not None:
        rate_map: dict[float, VATRate] = {0.0: VATRate.ZERO, 0.05: VATRate.FIVE, 0.08: VATRate.EIGHT, 0.10: VATRate.TEN}
        count_query = count_query.where(Invoice.vat_rate == rate_map[vat_rate])
    if seller_name:
        count_query = count_query.where(Invoice.seller_name.ilike(f"%{seller_name}%"))
    if buyer_name:
        count_query = count_query.where(Invoice.buyer_name.ilike(f"%{buyer_name}%"))
    if verification_status == "verified":
        count_query = count_query.where(Invoice.einvoice_verified == True)
    elif verification_status == "pending":
        count_query = count_query.where(or_(Invoice.einvoice_verified == False, Invoice.einvoice_verified.is_(None)))
    if direction_clause is not None:
        count_query = count_query.where(direction_clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Main query with pagination (direction filter already applied)
    query = query.order_by(Invoice.invoice_date.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    invoices = result.scalars().all()

    return {
        "items": [_invoice_dict(inv) for inv in invoices],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
    }


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_dict(inv)


@router.post("/{invoice_id}/verify-einvoice")
async def verify_einvoice(invoice_id: str, current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Verify invoice against GDT e-invoice portal.
    """
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not (inv.invoice_series and inv.invoice_number):
        raise HTTPException(status_code=400, detail="Cannot verify: missing invoice series or number")

    from app.services.einvoice import GDTInvoiceVerificationService
    service = GDTInvoiceVerificationService()
    verification = await service.verify_invoice(
        invoice_series=inv.invoice_series,
        invoice_number=inv.invoice_number,
        tax_code=inv.seller_tax_code or inv.buyer_tax_code,
    )

    inv.einvoice_verified = bool(verification.get("verified"))
    if verification.get("verified"):
        inv.einvoice_verified_at = datetime.utcnow()
    else:
        inv.einvoice_verified_at = None
    inv.notes = (inv.notes or "") + "\nManual GDT verification result: " + json.dumps(verification, ensure_ascii=False)
    await db.commit()
    response = _invoice_dict(inv)
    response["gdt_verification"] = verification
    return response


def _invoice_dict(inv: Invoice) -> dict:
    return {
        "id": inv.id,
        "company_id": inv.company_id,
        "document_id": inv.document_id,
        "invoice_series": inv.invoice_series,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "invoice_type": inv.invoice_type,
        "currency_code": getattr(inv, "currency_code", "VND"),
        "seller_name": inv.seller_name,
        "seller_tax_code": inv.seller_tax_code,
        "seller_address": inv.seller_address,
        "buyer_name": inv.buyer_name,
        "buyer_tax_code": inv.buyer_tax_code,
        "buyer_address": inv.buyer_address,
        "subtotal_amount": inv.subtotal_amount,
        "vat_rate": inv.vat_rate,
        "vat_amount": inv.vat_amount,
        "total_amount": inv.total_amount,
        "line_items": inv.line_items or [],
        "einvoice_code": inv.einvoice_code,
        "einvoice_verified": inv.einvoice_verified,
        "einvoice_verified_at": inv.einvoice_verified_at,
        "notes": inv.notes,
        "gdt_verification": None,
        "confidence": None,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }
