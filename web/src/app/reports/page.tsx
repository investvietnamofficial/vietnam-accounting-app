"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AlertTriangle, Download } from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import { useCITProvisional, useExportVATDeclaration, useVATSummary } from "@/hooks/useApi";
import type { VATSummary } from "@/types";

const vnd = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });

type VatAdjustments = {
  previousVatCredit: number;
  importPurchaseValue: number;
  importPurchaseVat: number;
  deductibleInputVatOverride: number | null;
  adjustmentDecrease: number;
  adjustmentIncrease: number;
  transferredVatCredit: number;
  investmentProjectOffsetVat: number;
  refundRequestedVat: number;
};

type CitAdjustments = {
  nonDeductibleExpenses: number;
  lossCarriedForward: number;
  citPaidYtd: number;
  annualCitEstimate: number | null;
  citRate: number;
};

const defaultVatAdjustments: VatAdjustments = {
  previousVatCredit: 0,
  importPurchaseValue: 0,
  importPurchaseVat: 0,
  deductibleInputVatOverride: null,
  adjustmentDecrease: 0,
  adjustmentIncrease: 0,
  transferredVatCredit: 0,
  investmentProjectOffsetVat: 0,
  refundRequestedVat: 0,
};

const defaultCitAdjustments: CitAdjustments = {
  nonDeductibleExpenses: 0,
  lossCarriedForward: 0,
  citPaidYtd: 0,
  annualCitEstimate: null,
  citRate: 0.2,
};

export default function ReportsPage() {
  const { user, logout } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [periodType, setPeriodType] = useState<"monthly" | "quarterly">("quarterly");
  const [period, setPeriod] = useState(Math.floor(now.getMonth() / 3) + 1);
  const [vatAdjustments, setVatAdjustments] = useState<VatAdjustments>(defaultVatAdjustments);
  const [citAdjustments, setCitAdjustments] = useState<CitAdjustments>(defaultCitAdjustments);

  const quarter = periodType === "quarterly" ? period : Math.floor((period - 1) / 3) + 1;
  const vat = useVATSummary(year, period, periodType, vatAdjustments);
  const cit = useCITProvisional(year, quarter, citAdjustments);
  const exportVat = useExportVATDeclaration();

  const declarationRows = useMemo(() => {
    const fields = vat.data?.filing_fields ?? {};
    return [
      ["[22]", "Khau tru ky truoc chuyen sang", fields["22"]],
      ["[23]", "Gia tri mua vao", fields["23"]],
      ["[24]", "Thue GTGT mua vao", fields["24"]],
      ["[25]", "Thue GTGT duoc khau tru ky nay", fields["25"]],
      ["[34]", "Tong doanh thu ban ra", fields["34"]],
      ["[35]", "Tong thue GTGT ban ra", fields["35"]],
      ["[36]", "Thue GTGT phat sinh trong ky", fields["36"]],
      ["[40]", "Thue GTGT con phai nop", fields["40"]],
      ["[41]", "Thue GTGT chua khau tru het", fields["41"]],
      ["[43]", "Thue GTGT duoc khau tru chuyen ky sau", fields["43"]],
    ];
  }, [vat.data]);

  const rateRows = useMemo(
    () => (vat.data?.by_rate ?? []).filter((row: VATSummary["by_rate"][number]) => row.input_amount || row.output_amount || row.input_vat || row.output_vat),
    [vat.data]
  );

  return (
    <ProtectedPage>
      <div className="flex min-h-screen bg-slate-50 text-slate-950">
        <Sidebar />
        <main className="flex-1">
          <header className="border-b bg-white">
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm text-slate-500">{user?.email}</p>
                <h1 className="text-2xl font-semibold">Tax Reports</h1>
              </div>
              <nav className="flex flex-wrap items-center gap-1 text-sm">
                <Link className="rounded-md px-2 py-1.5 text-slate-600 hover:bg-slate-100" href="/reports/vat-summary">VAT Summary</Link>
                <Link className="rounded-md bg-slate-900 px-2 py-1.5 text-white" href="/reports">Overview</Link>
                <Link className="rounded-md px-2 py-1.5 text-slate-600 hover:bg-slate-100" href="/reports/sales-invoices">Sales Invoices</Link>
                <Link className="rounded-md px-2 py-1.5 text-slate-600 hover:bg-slate-100" href="/reports/purchase-invoices">Purchase Invoices</Link>
                <Link className="rounded-md px-2 py-1.5 text-slate-600 hover:bg-slate-100" href="/reports/exceptions">Exceptions</Link>
                <button className="rounded-md px-2 py-1.5 text-slate-600 hover:bg-slate-100" onClick={logout}>Sign out</button>
              </nav>
            </div>
          </header>

          <section className="px-6 py-6">
          <div className="mb-6 flex flex-wrap items-end gap-3 rounded-lg border bg-white p-4">
            <label className="grid gap-1 text-sm">
              <span className="text-slate-500">Year</span>
              <input
                className="h-10 w-28 rounded-md border px-3"
                type="number"
                value={year}
                title="Select the filing year for VAT and CIT calculations."
                aria-label="Year"
                onChange={(event) => setYear(Number(event.target.value))}
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="text-slate-500">Period type</span>
              <select
                className="h-10 rounded-md border px-3"
                value={periodType}
                title="Switch between monthly and quarterly VAT declaration views."
                aria-label="Period type"
                onChange={(event) => {
                  const next = event.target.value as "monthly" | "quarterly";
                  setPeriodType(next);
                  setPeriod(1);
                }}
              >
                <option value="quarterly">Quarterly</option>
                <option value="monthly">Monthly</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm">
              <span className="text-slate-500">Period</span>
              <select className="h-10 rounded-md border px-3" value={period} title="Choose the month or quarter to report." aria-label="Period" onChange={(event) => setPeriod(Number(event.target.value))}>
                {Array.from({ length: periodType === "quarterly" ? 4 : 12 }, (_, index) => index + 1).map((value) => (
                  <option key={value} value={value}>{periodType === "quarterly" ? `Q${value}` : `Month ${value}`}</option>
                ))}
              </select>
            </label>
            <button
              onClick={() => exportVat.mutate({ year, period, periodType, format: "xlsx", params: vatAdjustments })}
              title="Download the current 01/GTGT declaration and annexes as an Excel workbook."
              className="ml-auto inline-flex h-10 items-center gap-2 rounded-md bg-emerald-700 px-4 text-sm font-medium text-white hover:bg-emerald-800"
            >
              <Download size={16} /> Export 01/GTGT XLSX
            </button>
          </div>

          {vat.data?.validation_issues?.length ? (
            <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="mb-2 inline-flex items-center gap-2 font-medium">
                <AlertTriangle size={16} /> Validation issues
              </div>
              <ul className="space-y-1">
                {vat.data.validation_issues.map((issue: string) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mb-6 grid gap-4 md:grid-cols-4">
            <Metric label="Input VAT [25]" tooltip="Deductible input VAT recognized for the current filing period." value={vnd.format(vat.data?.input_vat_total ?? 0)} />
            <Metric label="Output VAT [35]" tooltip="Total output VAT arising from sales in the current filing period." value={vnd.format(vat.data?.output_vat_total ?? 0)} />
            <Metric label="VAT payable [40]" tooltip="Final VAT payable after offsets, adjustments, and carryforwards." value={vnd.format(vat.data?.payable_vat ?? 0)} />
            <Metric label="Deadline" tooltip="Computed filing deadline based on the selected monthly or quarterly period." value={vat.data?.declaration_deadline ?? "-"} />
          </div>

          <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
            <section className="rounded-lg border bg-white p-4">
              <h2 className="mb-4 font-semibold">Declaration Inputs</h2>
              <div className="grid gap-3 md:grid-cols-2">
                <MoneyInput label="Previous VAT credit [22]" value={vatAdjustments.previousVatCredit} onChange={(value) => setVatAdjustments((current) => ({ ...current, previousVatCredit: value }))} />
                <MoneyInput label="Import purchase value [23a]" value={vatAdjustments.importPurchaseValue} onChange={(value) => setVatAdjustments((current) => ({ ...current, importPurchaseValue: value }))} />
                <MoneyInput label="Import purchase VAT [24a]" value={vatAdjustments.importPurchaseVat} onChange={(value) => setVatAdjustments((current) => ({ ...current, importPurchaseVat: value }))} />
                <MoneyInput label="Deductible input VAT override [25]" value={vatAdjustments.deductibleInputVatOverride ?? 0} allowBlank onChange={(value, blank) => setVatAdjustments((current) => ({ ...current, deductibleInputVatOverride: blank ? null : value }))} />
                <MoneyInput label="Adjustment decrease [37]" value={vatAdjustments.adjustmentDecrease} onChange={(value) => setVatAdjustments((current) => ({ ...current, adjustmentDecrease: value }))} />
                <MoneyInput label="Adjustment increase [38]" value={vatAdjustments.adjustmentIncrease} onChange={(value) => setVatAdjustments((current) => ({ ...current, adjustmentIncrease: value }))} />
                <MoneyInput label="Transferred VAT credit [39a]" value={vatAdjustments.transferredVatCredit} onChange={(value) => setVatAdjustments((current) => ({ ...current, transferredVatCredit: value }))} />
                <MoneyInput label="Project offset VAT [40b]" value={vatAdjustments.investmentProjectOffsetVat} onChange={(value) => setVatAdjustments((current) => ({ ...current, investmentProjectOffsetVat: value }))} />
                <MoneyInput label="Refund requested [42]" value={vatAdjustments.refundRequestedVat} onChange={(value) => setVatAdjustments((current) => ({ ...current, refundRequestedVat: value }))} />
              </div>
            </section>

            <section className="rounded-lg border bg-white p-4">
              <h2 className="mb-4 font-semibold">Declaration Fields</h2>
              <div className="grid gap-3 md:grid-cols-2">
                {declarationRows.map(([code, label, value]) => (
                  <Line key={code} label={`${code} ${label}`} value={typeof value === "number" ? vnd.format(value) : String(value ?? "-")} strong={code === "[40]" || code === "[43]"} />
                ))}
              </div>
            </section>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <section className="rounded-lg border bg-white p-4">
              <h2 className="mb-3 font-semibold">VAT Rate Breakdown</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b text-slate-500">
                    <tr>
                      <th title="Declared VAT bucket for this row." className="py-2">Rate</th>
                      <th title="Total purchase value before VAT for this rate." className="text-right">Input base</th>
                      <th title="Deductible input VAT for this rate." className="text-right">Input VAT</th>
                      <th title="Total sales value before VAT for this rate." className="text-right">Output base</th>
                      <th title="Output VAT arising from sales at this rate." className="text-right">Output VAT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rateRows.map((row: VATSummary["by_rate"][number]) => (
                      <tr key={row.rate} className="border-b last:border-0">
                        <td className="py-2">{row.rate}</td>
                        <td className="text-right">{vnd.format(row.input_amount ?? 0)}</td>
                        <td className="text-right">{vnd.format(row.input_vat ?? 0)}</td>
                        <td className="text-right">{vnd.format(row.output_amount ?? 0)}</td>
                        <td className="text-right">{vnd.format(row.output_vat ?? 0)}</td>
                      </tr>
                    ))}
                    {!rateRows.length && (
                      <tr><td className="py-8 text-center text-slate-500" colSpan={5}>No invoice activity for this period.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="rounded-lg border bg-white p-4">
              <h2 className="mb-3 font-semibold">CIT Provisional Inputs</h2>
              <div className="grid gap-3">
                <MoneyInput label="Non-deductible expenses" value={citAdjustments.nonDeductibleExpenses} onChange={(value) => setCitAdjustments((current) => ({ ...current, nonDeductibleExpenses: value }))} />
                <MoneyInput label="Loss carried forward" value={citAdjustments.lossCarriedForward} onChange={(value) => setCitAdjustments((current) => ({ ...current, lossCarriedForward: value }))} />
                <MoneyInput label="CIT paid YTD" value={citAdjustments.citPaidYtd} onChange={(value) => setCitAdjustments((current) => ({ ...current, citPaidYtd: value }))} />
                <MoneyInput label="Annual CIT estimate (Q4 rule)" value={citAdjustments.annualCitEstimate ?? 0} allowBlank onChange={(value, blank) => setCitAdjustments((current) => ({ ...current, annualCitEstimate: blank ? null : value }))} />
                <RateInput label="CIT rate" value={citAdjustments.citRate} onChange={(value) => setCitAdjustments((current) => ({ ...current, citRate: value }))} />
              </div>
            </section>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_1fr]">
            <section className="rounded-lg border bg-white p-4">
              <h2 className="mb-3 font-semibold">CIT Provisional</h2>
              <dl className="space-y-3 text-sm">
                <Line label="Revenue" value={vnd.format(cit.data?.revenue ?? 0)} />
                <Line label="Deductible expenses" value={vnd.format(cit.data?.deductible_expenses ?? 0)} />
                <Line label="Other income" value={vnd.format(cit.data?.other_income ?? 0)} />
                <Line label="Other expenses" value={vnd.format(cit.data?.other_expenses ?? 0)} />
                <Line label="Accounting profit" value={vnd.format(cit.data?.accounting_profit ?? 0)} />
                <Line label="Taxable income" value={vnd.format(cit.data?.taxable_income ?? 0)} />
                <Line label="CIT liability YTD" value={vnd.format(cit.data?.cit_amount ?? 0)} />
                <Line label="Already paid" value={vnd.format(cit.data?.already_paid ?? 0)} />
                <Line label="Minimum cumulative payment" value={cit.data?.minimum_cumulative_payment != null ? vnd.format(cit.data.minimum_cumulative_payment) : "-"} />
                <Line label="Amount due" value={vnd.format(cit.data?.amount_due ?? 0)} strong />
                <Line label="Due date" value={cit.data?.due_date ?? "-"} />
              </dl>
            </section>

            <section className="rounded-lg border bg-white p-4">
              <h2 className="mb-3 font-semibold">Annex Totals</h2>
              <dl className="space-y-3 text-sm">
                <Line label="Purchases count" value={String(vat.data?.purchase_annex?.totals.count ?? 0)} />
                <Line label="Purchases taxable value" value={vnd.format(vat.data?.purchase_annex?.totals.taxable_value ?? 0)} />
                <Line label="Purchases VAT" value={vnd.format(vat.data?.purchase_annex?.totals.vat_amount ?? 0)} />
                <Line label="Sales count" value={String(vat.data?.sales_annex?.totals.count ?? 0)} />
                <Line label="Sales taxable value" value={vnd.format(vat.data?.sales_annex?.totals.taxable_value ?? 0)} />
                <Line label="Sales VAT" value={vnd.format(vat.data?.sales_annex?.totals.vat_amount ?? 0)} />
              </dl>
            </section>
          </div>
        </section>
        </main>
        </div>
    </ProtectedPage>
  );
}

function Metric({ label, value, tooltip }: { label: string; value: string; tooltip: string }) {
  return (
    <div title={tooltip} className="rounded-lg border bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Line({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-500">{label}</dt>
      <dd className={strong ? "font-semibold" : ""}>{value}</dd>
    </div>
  );
}

function MoneyInput({
  label,
  value,
  onChange,
  allowBlank = false,
}: {
  label: string;
  value: number;
  onChange: (value: number, blank?: boolean) => void;
  allowBlank?: boolean;
}) {
  const displayValue = allowBlank && value === 0 ? "" : String(value);
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-slate-500">{label}</span>
      <input
        className="h-10 rounded-md border px-3"
        type="number"
        min={0}
        value={displayValue}
        title={`Enter ${label.toLowerCase()}. Leave blank only when you want the system to derive it automatically.`}
        aria-label={label}
        onChange={(event) => {
          if (allowBlank && event.target.value === "") {
            onChange(0, true);
            return;
          }
          onChange(Number(event.target.value || 0), false);
        }}
      />
    </label>
  );
}

function RateInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-slate-500">{label}</span>
      <input
        className="h-10 rounded-md border px-3"
        type="number"
        min={0}
        max={1}
        step="0.01"
        value={value}
        title="Enter the applicable CIT rate as a decimal. Example: 0.2 for 20%."
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value || 0))}
      />
    </label>
  );
}
