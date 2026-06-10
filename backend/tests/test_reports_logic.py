from datetime import UTC, datetime

from app.api.routes.reports import _aggregate_cit_bases, _build_vat_declaration_summary
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
    assert deductible_expenses == 700_000_000
    assert other_income == 50_000_000
    assert other_expenses == 20_000_000
