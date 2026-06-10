"""Invoice CRUD and verification routes."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Invoice
from app.services.einvoice import GDTInvoiceVerificationService

router = APIRouter()

@router.get("/")
async def list_invoices(page: int = 1, page_size: int = 20,
                        current_user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TODO (Codex): Add filters for date range, seller, amount, VAT rate, verification status."""
    total_result = await db.execute(
        select(func.count()).select_from(Invoice).where(Invoice.company_id == current_user.company_id)
    )
    result = await db.execute(
        select(Invoice).where(Invoice.company_id == current_user.company_id)
        .order_by(Invoice.invoice_date.desc()).offset((page-1)*page_size).limit(page_size)
    )
    invoices = result.scalars().all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total_result.scalar() or 0,
        "items": [_invoice_dict(inv) for inv in invoices],
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
