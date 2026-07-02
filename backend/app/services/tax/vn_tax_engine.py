"""
Vietnam tax rules helpers used by filing-facing reporting endpoints.

References used for the implemented rules:
- Thong tu 80/2021/TT-BTC, Mau 01/GTGT formulas
- Luat Quan ly thue 38/2019/QH14, Dieu 44 and Dieu 55
- Nghi dinh 126/2020/ND-CP, sua doi boi Nghi dinh 91/2022/ND-CP
- Circular 79/1998/TT-BTC tax-code checksum structure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import TYPE_CHECKING

from app.models import VATRate

if TYPE_CHECKING:
    from app.models import Invoice


# ---------------------------------------------------------------------------
# Shared numeric helpers
# ---------------------------------------------------------------------------

VND_QUANT = Decimal("1")


def round_vnd(value: Decimal | int | float | str) -> int:
    return int(Decimal(str(value)).quantize(VND_QUANT, rounding=ROUND_HALF_UP))


def clamp_non_negative(value: int) -> int:
    return max(0, int(value))


# ---------------------------------------------------------------------------
# VAT Rules
# ---------------------------------------------------------------------------

VAT_RATE_MAP: dict[VATRate, Decimal] = {
    VATRate.ZERO: Decimal("0"),
    VATRate.FIVE: Decimal("0.05"),
    VATRate.EIGHT: Decimal("0.08"),
    VATRate.TEN: Decimal("0.10"),
    VATRate.EXEMPT: Decimal("0"),
    VATRate.NOT_APPLICABLE: Decimal("0"),
}


@dataclass
class VATCalculation:
    subtotal: int
    vat_rate: VATRate
    vat_amount: int
    total: int


def calculate_vat(subtotal_vnd: int, rate: VATRate) -> VATCalculation:
    rate_decimal = VAT_RATE_MAP[rate]
    vat_amount = round_vnd(Decimal(subtotal_vnd) * rate_decimal)
    return VATCalculation(
        subtotal=subtotal_vnd,
        vat_rate=rate,
        vat_amount=vat_amount,
        total=subtotal_vnd + vat_amount,
    )


def validate_vat_amount(subtotal: int, vat_rate: VATRate, declared_vat: int) -> tuple[bool, int]:
    expected = calculate_vat(subtotal, vat_rate).vat_amount
    return abs(expected - declared_vat) <= 1, expected


# ---------------------------------------------------------------------------
# Journal Entry Templates
# ---------------------------------------------------------------------------

@dataclass
class JournalLine:
    account_code: str
    debit: int = 0
    credit: int = 0
    description: str = ""


def generate_purchase_journal_entries(
    subtotal: int,
    vat_amount: int,
    total: int,
    vat_rate: VATRate,
    description: str,
    accounting_standard: str = "TT200",
) -> list[JournalLine]:
    if vat_rate in (VATRate.EXEMPT, VATRate.NOT_APPLICABLE):
        return [
            JournalLine("156", debit=subtotal, description=f"Hang mua: {description}"),
            JournalLine("331", credit=total, description=f"Phai tra NCC: {description}"),
        ]

    return [
        JournalLine("156", debit=subtotal, description=f"Hang mua: {description}"),
        JournalLine("1331", debit=vat_amount, description=f"Thue GTGT dau vao: {description}"),
        JournalLine("331", credit=total, description=f"Phai tra NCC: {description}"),
    ]


def generate_sales_journal_entries(
    subtotal: int,
    vat_amount: int,
    total: int,
    vat_rate: VATRate,
    description: str,
    accounting_standard: str = "TT200",
) -> list[JournalLine]:
    if vat_rate in (VATRate.EXEMPT, VATRate.NOT_APPLICABLE):
        return [
            JournalLine("131", debit=total, description=f"Phai thu KH: {description}"),
            JournalLine("511", credit=subtotal, description=f"Doanh thu: {description}"),
        ]

    return [
        JournalLine("131", debit=total, description=f"Phai thu KH: {description}"),
        JournalLine("511", credit=subtotal, description=f"Doanh thu: {description}"),
        JournalLine("3331", credit=vat_amount, description=f"Thue GTGT dau ra: {description}"),
    ]


# ---------------------------------------------------------------------------
# MST (Tax Code) Validation
# ---------------------------------------------------------------------------

MST_CHECKSUM_WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)


def normalize_tax_code(tax_code: str | None) -> str:
    if not tax_code:
        return ""
    return "".join(ch for ch in str(tax_code) if ch.isdigit())


def calculate_mst_check_digit(first_nine_digits: str) -> int:
    if len(first_nine_digits) != 9 or not first_nine_digits.isdigit():
        raise ValueError("MST base must contain exactly 9 digits")

    checksum_total = sum(int(digit) * weight for digit, weight in zip(first_nine_digits, MST_CHECKSUM_WEIGHTS))
    remainder = checksum_total % 11
    check_digit = 10 - remainder
    if check_digit >= 10:
        return 0
    return check_digit


def validate_mst(tax_code: str) -> bool:
    """
    Validate a Vietnamese tax code.

    10-digit MST:
    - first 9 digits are the tax-body and serial structure
    - 10th digit is the checksum

    13-digit dependent-unit MST:
    - first 10 digits are the parent MST
    - last 3 digits are the dependent-unit sequence 001..999
    """
    digits = normalize_tax_code(tax_code)
    if len(digits) == 10:
        return digits[-1] == str(calculate_mst_check_digit(digits[:9]))
    if len(digits) == 13:
        branch_code = digits[10:]
        return validate_mst(digits[:10]) and branch_code != "000"
    return False


# ---------------------------------------------------------------------------
# CIT (Corporate Income Tax) Rules
# ---------------------------------------------------------------------------

class CITRate(str, Enum):
    STANDARD = "0.20"
    PREFERENTIAL = "0.10"
    SME = "0.17"


CIT_STANDARD_RATE = Decimal(CITRate.STANDARD.value)
CIT_PREFERENTIAL_RATE = Decimal(CITRate.PREFERENTIAL.value)
CIT_SME_RATE = Decimal(CITRate.SME.value)


@dataclass
class CITCalculation:
    revenue: int
    deductible_expenses: int
    other_income: int
    other_expenses: int
    accounting_profit: int
    non_deductible_expenses: int
    loss_carried_forward: int
    taxable_income: int
    cit_rate: Decimal
    cit_liability_ytd: int
    cit_paid_ytd: int
    amount_due: int
    annual_cit_estimate: int | None
    minimum_cumulative_payment: int | None


def calculate_quarterly_cit_provision(
    revenue: int,
    deductible_expenses: int,
    *,
    other_income: int = 0,
    other_expenses: int = 0,
    non_deductible_expenses: int = 0,
    loss_carried_forward: int = 0,
    cit_paid_ytd: int = 0,
    cit_rate: Decimal = CIT_STANDARD_RATE,
    annual_cit_estimate: int | None = None,
    quarter: int | None = None,
) -> CITCalculation:
    accounting_profit = revenue + other_income - deductible_expenses - other_expenses
    taxable_income = clamp_non_negative(accounting_profit + non_deductible_expenses - loss_carried_forward)
    cit_liability_ytd = round_vnd(Decimal(taxable_income) * cit_rate)
    minimum_cumulative_payment = None

    amount_due = clamp_non_negative(cit_liability_ytd - cit_paid_ytd)
    if quarter == 4 and annual_cit_estimate is not None:
        minimum_cumulative_payment = round_vnd(Decimal(annual_cit_estimate) * Decimal("0.80"))
        amount_due = max(amount_due, clamp_non_negative(minimum_cumulative_payment - cit_paid_ytd))

    return CITCalculation(
        revenue=revenue,
        deductible_expenses=deductible_expenses,
        other_income=other_income,
        other_expenses=other_expenses,
        accounting_profit=accounting_profit,
        non_deductible_expenses=non_deductible_expenses,
        loss_carried_forward=loss_carried_forward,
        taxable_income=taxable_income,
        cit_rate=cit_rate,
        cit_liability_ytd=cit_liability_ytd,
        cit_paid_ytd=cit_paid_ytd,
        amount_due=amount_due,
        annual_cit_estimate=annual_cit_estimate,
        minimum_cumulative_payment=minimum_cumulative_payment,
    )


# ---------------------------------------------------------------------------
# Declaration deadlines
# ---------------------------------------------------------------------------

def _move_to_next_business_day(value: date) -> date:
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def get_vat_declaration_deadline(year: int, period: int, period_type: str = "monthly") -> str:
    if period_type == "monthly":
        next_month = period % 12 + 1
        next_year = year if period < 12 else year + 1
        deadline = date(next_year, next_month, 20)
    else:
        end_month = period * 3
        next_month = end_month % 12 + 1
        next_year = year if end_month < 12 else year + 1
        if next_month == 12:
            month_after = date(next_year + 1, 1, 1)
        else:
            month_after = date(next_year, next_month + 1, 1)
        deadline = month_after - timedelta(days=1)

    return _move_to_next_business_day(deadline).isoformat()


def get_cit_quarter_payment_deadline(year: int, quarter: int) -> str:
    if quarter < 1 or quarter > 4:
        raise ValueError("Quarter must be between 1 and 4")
    if quarter == 4:
        deadline = date(year + 1, 1, 30)
    else:
        deadline = date(year, quarter * 3 + 1, 30)
    return _move_to_next_business_day(deadline).isoformat()


# ---------------------------------------------------------------------------
# Invoice Validation / Issue Detection
# ---------------------------------------------------------------------------


@dataclass
class InvoiceIssue:
    type: str
    message: str
    invoice_ids: list[str]
    count: int


@dataclass
class InvoiceValidationResult:
    issues: list[InvoiceIssue]
    total_invoices: int


def detect_duplicate_invoices(invoices: list["Invoice"]) -> InvoiceIssue | None:
    """
    Detect invoices with the same invoice_number + seller_name + invoice_date.
    Groups by key and returns any groups with > 1 invoice.
    """
    seen: dict[str, list[str]] = {}
    for inv in invoices:
        if not inv.invoice_number or not inv.seller_name or not inv.invoice_date:
            continue
        date_str = inv.invoice_date.date().isoformat() if hasattr(inv.invoice_date, "date") else str(inv.invoice_date)[:10]
        key = f"{inv.invoice_number}|{inv.seller_name.strip().lower()}|{date_str}"
        seen.setdefault(key, []).append(inv.id)

    dup_groups = [ids for ids in seen.values() if len(ids) > 1]
    if not dup_groups:
        return None

    flat_ids: list[str] = []
    for group in dup_groups:
        flat_ids.extend(group)

    return InvoiceIssue(
        type="duplicate",
        message=(
            f"Found {len(dup_groups)} group(s) of duplicate invoices: "
            f"same invoice_number + seller_name + invoice_date"
        ),
        invoice_ids=flat_ids,
        count=len(flat_ids),
    )


def detect_missing_mst(invoices: list["Invoice"]) -> InvoiceIssue | None:
    """
    Detect invoices where seller_tax_code is null or empty.
    """
    affected = [
        inv.id
        for inv in invoices
        if not (inv.seller_tax_code and inv.seller_tax_code.strip())
    ]
    if not affected:
        return None

    return InvoiceIssue(
        type="missing_mst",
        message="Invoice(s) missing seller MST (tax code is null or empty)",
        invoice_ids=affected,
        count=len(affected),
    )


def detect_low_confidence(invoices: list["Invoice"], threshold: float = 0.8) -> InvoiceIssue | None:
    """
    Detect invoices where extraction_confidence < threshold.
    Only checks invoices that have a confidence value set.
    """
    affected = [
        inv.id
        for inv in invoices
        if inv.extraction_confidence is not None and float(inv.extraction_confidence) < threshold
    ]
    if not affected:
        return None

    return InvoiceIssue(
        type="low_confidence",
        message=f"Invoice(s) with extraction confidence below {threshold}",
        invoice_ids=affected,
        count=len(affected),
    )


def detect_vat_mismatch(invoices: list["Invoice"]) -> InvoiceIssue | None:
    """
    Detect invoices where declared VAT amount does not match subtotal * vat_rate.
    Uses the same tolerance (≤ 1 VND) as validate_vat_amount().
    """
    affected = []
    for inv in invoices:
        subtotal = int(inv.subtotal_amount or 0)
        declared_vat = int(inv.vat_amount or 0)
        total = int(inv.total_amount or 0)

        # Flag invoices where subtotal and total are both zero — likely failed extraction
        if subtotal == 0 and total == 0:
            affected.append(inv.id)
            continue

        # Skip only if both subtotal AND declared_vat are zero (truly zero-value invoice)
        if subtotal == 0 and declared_vat == 0:
            continue

        expected_vat = round_vnd(Decimal(subtotal) * VAT_RATE_MAP.get(inv.vat_rate, Decimal("0")))
        if abs(expected_vat - declared_vat) > 1:
            affected.append(inv.id)

    if not affected:
        return None

    return InvoiceIssue(
        type="vat_mismatch",
        message="Invoice(s) where declared VAT amount does not match subtotal × VAT rate",
        invoice_ids=affected,
        count=len(affected),
    )


def validate_invoices(invoices: list["Invoice"]) -> InvoiceValidationResult:
    """
    Run all invoice validation checks and return structured results.
    """
    issues: list[InvoiceIssue] = []

    for detector in (
        detect_missing_mst,
        detect_duplicate_invoices,
        detect_low_confidence,
        detect_vat_mismatch,
    ):
        issue = detector(invoices)
        if issue:
            issues.append(issue)

    return InvoiceValidationResult(issues=issues, total_invoices=len(invoices))
