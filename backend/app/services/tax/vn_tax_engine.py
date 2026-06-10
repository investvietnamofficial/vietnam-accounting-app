"""
Vietnam tax rules helpers used by filing-facing reporting endpoints.

References used for the implemented rules:
- Thong tu 80/2021/TT-BTC, Mau 01/GTGT formulas
- Luat Quan ly thue 38/2019/QH14, Dieu 44 and Dieu 55
- Nghi dinh 126/2020/ND-CP, sua doi boi Nghi dinh 91/2022/ND-CP
- Circular 79/1998/TT-BTC tax-code checksum structure
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from app.models import VATRate


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
