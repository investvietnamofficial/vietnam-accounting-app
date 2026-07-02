from decimal import Decimal

from app.services.extraction.claude_extractor import ExtractionService
from app.services.tax.vn_tax_engine import (
    CIT_STANDARD_RATE,
    calculate_mst_check_digit,
    calculate_quarterly_cit_provision,
    get_cit_quarter_payment_deadline,
    get_vat_declaration_deadline,
    validate_mst,
)


def test_calculate_mst_check_digit_and_validate_10_digit_code():
    base = "010124315"
    check_digit = calculate_mst_check_digit(base)
    tax_code = f"{base}{check_digit}"

    assert check_digit == 0
    assert validate_mst(tax_code) is True
    assert validate_mst("0101243151") is False


def test_validate_mst_accepts_13_digit_branch_code():
    assert validate_mst("0101243150001") is True
    assert validate_mst("0101243150000") is False


def test_vat_deadline_rolls_to_next_business_day():
    assert get_vat_declaration_deadline(2026, 1, "monthly") == "2026-02-20"
    assert get_vat_declaration_deadline(2026, 1, "quarterly") == "2026-04-30"


def test_cit_quarter_payment_deadline_rolls_weekends():
    assert get_cit_quarter_payment_deadline(2026, 1) == "2026-04-30"
    assert get_cit_quarter_payment_deadline(2026, 4) == "2027-02-01"


def test_calculate_quarterly_cit_provision_uses_ytd_taxable_income_and_q4_floor():
    result = calculate_quarterly_cit_provision(
        revenue=1_000_000_000,
        deductible_expenses=700_000_000,
        non_deductible_expenses=20_000_000,
        loss_carried_forward=10_000_000,
        cit_paid_ytd=40_000_000,
        cit_rate=CIT_STANDARD_RATE,
        annual_cit_estimate=120_000_000,
        quarter=4,
    )

    assert result.accounting_profit == 300_000_000
    assert result.taxable_income == 310_000_000
    assert result.cit_liability_ytd == 62_000_000
    assert result.minimum_cumulative_payment == 96_000_000
    assert result.amount_due == 56_000_000
    assert result.cit_rate == Decimal("0.20")


def test_amount_normalization_vietnamese_and_european():
    """
    Regression: extraction must correctly parse Vietnamese (dot=thousand-sep)
    and European (comma=decimal) amount formats into integer VND.
    """
    extractor = ExtractionService()

    # Vietnamese dot-as-thousand-separator: 1.500.000 = 1,500,000
    assert extractor._normalize_amount_string("1.500.000") == 1_500_000
    # European decimal comma truncated: 1.500.000,50 → 1.500.000 → 1500000
    assert extractor._normalize_amount_string("1.500.000,50") == 1_500_000
    # Plain integer string
    assert extractor._normalize_amount_string("1500000") == 1_500_000
    # Mixed formats
    assert extractor._normalize_amount_string("10.000.000") == 10_000_000
