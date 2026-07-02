from datetime import UTC, datetime

from app.api.routes.reports import (
    _aggregate_cit_bases,
    _build_vat_declaration_summary,
    _invoice_report_row,
    _invoice_direction,
    _vat_rate_float,
)
from app.models import Company, Invoice, JournalEntry, JournalEntryLine, JournalEntryStatus, VATRate


def _company() -> Company:
    return Company(
        id="company-1",
        name="Cong ty TNHH Demo Viet Nam",
        tax_code="0101243150",
        accounting_standard="TT200",
    )


def _invoice(
    *,
    invoice_id: str,
    direction: str,
    subtotal: int,
    vat_rate: VATRate,
    vat_amount: int,
    total_amount: int,
) -> Invoice:
    company = _company()
    if direction == "sale":
        seller_tax_code = company.tax_code
        buyer_tax_code = "0312345678"
    else:
        seller_tax_code = "0312345678"
        buyer_tax_code = company.tax_code

    return Invoice(
        id=invoice_id,
        company_id=company.id,
        document_id=f"doc-{invoice_id}",
        invoice_date=datetime(2026, 3, 15, tzinfo=UTC),
        invoice_series="AA/26E",
        invoice_number=invoice_id[-3:],
        invoice_type="invoice_vat",
        currency_code="VND",
        seller_name="Seller" if direction == "purchase" else company.name,
        seller_tax_code=seller_tax_code,
        buyer_name="Buyer" if direction == "sale" else company.name,
        buyer_tax_code=buyer_tax_code,
        subtotal_amount=subtotal,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total_amount=total_amount,
        einvoice_verified=True,
    )


def test_build_vat_declaration_summary_populates_formulas_and_annexes():
    company = _company()
    invoices = [
        _invoice(invoice_id="inv-001", direction="purchase", subtotal=100_000_000, vat_rate=VATRate.TEN, vat_amount=10_000_000, total_amount=110_000_000),
        _invoice(invoice_id="inv-002", direction="sale", subtotal=200_000_000, vat_rate=VATRate.FIVE, vat_amount=10_000_000, total_amount=210_000_000),
        _invoice(invoice_id="inv-003", direction="sale", subtotal=150_000_000, vat_rate=VATRate.EIGHT, vat_amount=12_000_000, total_amount=162_000_000),
        _invoice(invoice_id="inv-004", direction="sale", subtotal=25_000_000, vat_rate=VATRate.EXEMPT, vat_amount=0, total_amount=25_000_000),
    ]

    summary = _build_vat_declaration_summary(
        invoices=invoices,
        company=company,
        year=2026,
        period=1,
        period_type="quarterly",
        previous_vat_credit=5_000_000,
        import_purchase_value=20_000_000,
        import_purchase_vat=2_000_000,
        deductible_input_vat_override=None,
        adjustment_decrease=1_000_000,
        adjustment_increase=500_000,
        transferred_vat_credit=500_000,
        investment_project_offset_vat=3_000_000,
        refund_requested_vat=1_000_000,
    )

    fields = summary["filing_fields"]
    assert fields["23"] == 120_000_000
    assert fields["24"] == 12_000_000
    assert fields["25"] == 12_000_000
    assert fields["30"] == 200_000_000
    assert fields["31"] == 10_000_000
    assert fields["32"] == 150_000_000
    assert fields["33"] == 12_000_000
    assert fields["34"] == 375_000_000
    assert fields["35"] == 22_000_000
    assert fields["36"] == 10_000_000
    assert fields["40"] == 2_000_000
    assert fields["43"] == 0
    assert summary["purchase_annex"]["totals"]["count"] == 1
    assert summary["sales_annex"]["totals"]["count"] == 3


def test_aggregate_cit_bases_uses_posted_journal_lines():
    entry = JournalEntry(
        id="je-1",
        company_id="company-1",
        entry_date=datetime(2026, 3, 31, tzinfo=UTC),
        description="Quarter close",
        status=JournalEntryStatus.POSTED,
        total_amount=0,
    )
    entry.lines = [
        JournalEntryLine(journal_entry_id="je-1", debit_account_code="131", credit_account_code="5111", amount=1_000_000_000),
        JournalEntryLine(journal_entry_id="je-1", debit_account_code="632", credit_account_code="156", amount=600_000_000),
        JournalEntryLine(journal_entry_id="je-1", debit_account_code="6421", credit_account_code="334", amount=100_000_000),
        JournalEntryLine(journal_entry_id="je-1", debit_account_code="811", credit_account_code="111", amount=20_000_000),
        JournalEntryLine(journal_entry_id="je-1", debit_account_code="111", credit_account_code="711", amount=50_000_000),
    ]

    revenue, deductible_expenses, other_income, other_expenses = _aggregate_cit_bases([entry])

    assert revenue == 1_000_000_000
    # 632 is deductible; 6421 is a sub-account (not in the explicit deductible list)
    # and is NOT swept by the catch-all — only the four specific codes are deductible
    assert deductible_expenses == 600_000_000
    assert other_income == 50_000_000
    assert other_expenses == 20_000_000


def test_vat_rate_float_returns_none_for_exempt_and_na():
    """C-1 regression: _vat_rate_float must not crash on EXEMPT or NOT_APPLICABLE."""
    assert _vat_rate_float(VATRate.EXEMPT) is None
    assert _vat_rate_float(VATRate.NOT_APPLICABLE) is None
    # Standard rates still work
    assert _vat_rate_float(VATRate.TEN) == 0.10
    assert _vat_rate_float(VATRate.FIVE) == 0.05
    assert _vat_rate_float(VATRate.EIGHT) == 0.08
    assert _vat_rate_float(VATRate.ZERO) == 0.0


def test_build_vat_declaration_summary_does_not_crash_on_exempt_or_na_invoices():
    """C-1 regression: VAT summary must not crash when invoice vat_rate is EXEMPT or NOT_APPLICABLE."""
    company = _company()
    invoices = [
        Invoice(
            id="inv-exempt",
            company_id=company.id,
            document_id="doc-exempt",
            invoice_date=datetime(2026, 3, 15, tzinfo=UTC),
            invoice_series="AA/26E",
            invoice_number="001",
            invoice_type="invoice_vat",
            currency_code="VND",
            seller_tax_code="0312345678",
            buyer_tax_code=company.tax_code,
            subtotal_amount=50_000_000,
            vat_rate=VATRate.EXEMPT,
            vat_amount=0,
            total_amount=50_000_000,
            einvoice_verified=False,
        ),
        Invoice(
            id="inv-na",
            company_id=company.id,
            document_id="doc-na",
            invoice_date=datetime(2026, 3, 15, tzinfo=UTC),
            invoice_series="AA/26E",
            invoice_number="002",
            invoice_type="invoice_vat",
            currency_code="VND",
            seller_tax_code="0312345678",
            buyer_tax_code=company.tax_code,
            subtotal_amount=75_000_000,
            vat_rate=VATRate.NOT_APPLICABLE,
            vat_amount=0,
            total_amount=75_000_000,
            einvoice_verified=False,
        ),
    ]

    # Must not raise
    summary = _build_vat_declaration_summary(
        invoices=invoices,
        company=company,
        year=2026,
        period=1,
        period_type="quarterly",
        previous_vat_credit=0,
        import_purchase_value=0,
        import_purchase_vat=0,
        deductible_input_vat_override=None,
        adjustment_decrease=0,
        adjustment_increase=0,
        transferred_vat_credit=0,
        investment_project_offset_vat=0,
        refund_requested_vat=0,
    )
    assert summary["filing_fields"]["23"] == 125_000_000  # exempt + na both counted in total base
    assert summary["purchase_annex"]["totals"]["count"] == 2


def test_invoice_direction_returns_uncertain_when_seller_tax_code_missing():
    """H-5 regression: invoice with no seller_tax_code returns (purchase, False)."""
    company = _company()
    invoice_no_seller = Invoice(
        id="inv-noseller",
        company_id=company.id,
        document_id="doc-noseller",
        invoice_date=datetime(2026, 3, 15, tzinfo=UTC),
        invoice_series="AA/26E",
        invoice_number="003",
        invoice_type="invoice_vat",
        currency_code="VND",
        seller_tax_code=None,  # missing seller MST
        buyer_tax_code=company.tax_code,
        subtotal_amount=10_000_000,
        vat_rate=VATRate.TEN,
        vat_amount=1_000_000,
        total_amount=11_000_000,
        einvoice_verified=False,
    )
    direction, is_certain = _invoice_direction(invoice_no_seller, company)
    assert direction == "purchase"
    assert is_certain is False


def test_vat_rate_float_handles_exempt_and_na():
    # Regression: exempt/NA VAT rates must not raise; they return None
    assert _vat_rate_float(VATRate.EXEMPT) is None
    assert _vat_rate_float(VATRate.NOT_APPLICABLE) is None
    # Standard rates convert to float fractions
    assert _vat_rate_float(VATRate.TEN) == 0.1
    assert _vat_rate_float(VATRate.FIVE) == 0.05
    assert _vat_rate_float(VATRate.EIGHT) == 0.08


def test_invoice_direction_uncertain_when_seller_mst_missing():
    # When seller_tax_code is None the direction is still determined as
    # "purchase" but is_certain=False (possible misread MST on a sales invoice)
    company = _company()
    inv_no_seller = Invoice(
        id="inv-no-seller",
        company_id=company.id,
        document_id="doc-no-seller",
        invoice_date=datetime(2026, 3, 15, tzinfo=UTC),
        invoice_series="AA/26E",
        invoice_number="001",
        invoice_type="invoice_vat",
        currency_code="VND",
        seller_name="Some Supplier",
        seller_tax_code=None,  # missing MST — uncertainty case
        buyer_name=company.name,
        buyer_tax_code=company.tax_code,
        subtotal_amount=10_000_000,
        vat_rate=VATRate.TEN,
        vat_amount=1_000_000,
        total_amount=11_000_000,
        einvoice_verified=False,
    )
    direction, is_certain = _invoice_direction(inv_no_seller, company)
    assert direction == "purchase"
    assert is_certain is False
