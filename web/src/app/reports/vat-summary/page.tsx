"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, RefreshCw, AlertTriangle } from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import { useVATSummary, useExportVATDeclaration } from "@/hooks/useApi";
import { apiClient } from "@/lib/api";

const vnd = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

export default function VatSummaryPage() {
  const { user, logout } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [periodType, setPeriodType] = useState<"monthly" | "quarterly">("quarterly");
  const [period, setPeriod] = useState(Math.floor(now.getMonth() / 3) + 1);
  const [hasGenerated, setHasGenerated] = useState(false);

  const vat = useVATSummary(year, period, periodType);
  const exportDecl = useExportVATDeclaration();

  const handleGenerate = () => {
    vat.refetch();
    setHasGenerated(true);
  };

  const handleExportExcel = async () => {
    try {
      const response = await apiClient.get("/reports/export/vat-declaration", {
        params: {
          year,
          period,
          period_type: periodType,
          format: "xlsx",
          previous_vat_credit: 0,
          import_purchase_value: 0,
          import_purchase_vat: 0,
          adjustment_decrease: 0,
          adjustment_increase: 0,
          transferred_vat_credit: 0,
          investment_project_offset_vat: 0,
          refund_requested_vat: 0,
        },
        responseType: "blob",
      });
      const blob = new Blob([response.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vat-summary-${year}-${periodType}-${period}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // fallback: trigger mutation
      exportDecl.mutate({
        year,
        period,
        periodType,
        format: "xlsx",
        params: {},
      });
    }
  };

  return (
    <ProtectedPage>
      <div className="flex min-h-screen bg-slate-50 text-slate-950">
        <Sidebar />
        <main className="flex-1">
          <header className="border-b bg-white">
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm text-slate-500">{user?.email}</p>
                <h1 className="text-2xl font-semibold">VAT Summary Report</h1>
              </div>
              <button className="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
            </div>
          </header>

          <section className="px-6 py-6 space-y-6">
          {/* Period Selector */}
          <div className="rounded-lg border bg-white p-4">
            <div className="flex flex-wrap items-end gap-3">
              <label className="grid gap-1 text-sm">
                <span className="text-slate-500">Year</span>
                <select
                  className="h-10 rounded-md border px-3"
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                >
                  {[now.getFullYear() - 2, now.getFullYear() - 1, now.getFullYear()].map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1 text-sm">
                <span className="text-slate-500">Period Type</span>
                <select
                  className="h-10 rounded-md border px-3"
                  value={periodType}
                  onChange={(e) => {
                    setPeriodType(e.target.value as "monthly" | "quarterly");
                    setPeriod(1);
                  }}
                >
                  <option value="quarterly">Quarterly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </label>

              <label className="grid gap-1 text-sm">
                <span className="text-slate-500">Period</span>
                <select
                  className="h-10 rounded-md border px-3"
                  value={period}
                  onChange={(e) => setPeriod(Number(e.target.value))}
                >
                  {Array.from({ length: periodType === "quarterly" ? 4 : 12 }, (_, i) => i + 1).map((v) => (
                    <option key={v} value={v}>
                      {periodType === "quarterly" ? `Q${v}` : `Month ${v}`}
                    </option>
                  ))}
                </select>
              </label>

              <button
                onClick={handleGenerate}
                disabled={vat.isFetching}
                className="inline-flex h-10 items-center gap-2 rounded-md bg-emerald-700 px-4 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                <RefreshCw size={15} className={vat.isFetching ? "animate-spin" : ""} />
                Generate Report
              </button>

              {hasGenerated && vat.data && (
                <button
                  onClick={handleExportExcel}
                  className="ml-auto inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm hover:bg-slate-100"
                >
                  <Download size={15} />
                  Export Excel
                </button>
              )}
            </div>
          </div>

          {/* Validation Issues */}
          {vat.data?.validation_issues && vat.data.validation_issues.length > 0 && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="mb-2 flex items-center gap-2 font-medium">
                <AlertTriangle size={16} />
                Validation Issues
              </div>
              <ul className="space-y-1">
                {vat.data.validation_issues.map((issue: string, i: number) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Summary Cards */}
          {vat.data && (
            <>
              {/* Company header */}
              <div className="rounded-lg border bg-white p-4 text-center">
                <h2 className="text-lg font-semibold">{vat.data.purchase_annex?.code ?? "VAT Declaration"}</h2>
                <p className="text-sm text-slate-500">
                  Filing period:{" "}
                  {periodType === "quarterly"
                    ? `Q${period}/${year}`
                    : `Month ${period}/${year}`}
                </p>
              </div>

              {/* Key metrics */}
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                  <p className="text-sm text-blue-600 font-medium">Input VAT (Deductible)</p>
                  <p className="mt-1 text-xl font-semibold text-blue-900">{vnd.format(vat.data.input_vat_total ?? 0)}</p>
                  <p className="mt-1 text-xs text-blue-600">[25] field</p>
                </div>
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                  <p className="text-sm text-amber-600 font-medium">Output VAT (Payable)</p>
                  <p className="mt-1 text-xl font-semibold text-amber-900">{vnd.format(vat.data.output_vat_total ?? 0)}</p>
                  <p className="mt-1 text-xs text-amber-600">[35] field</p>
                </div>
                <div
                  className={`rounded-lg border p-4 ${
                    (vat.data.payable_vat ?? 0) > 0
                      ? "border-red-200 bg-red-50"
                      : "border-emerald-200 bg-emerald-50"
                  }`}
                >
                  <p className={`text-sm font-medium ${(vat.data.payable_vat ?? 0) > 0 ? "text-red-600" : "text-emerald-600"}`}>
                    Net VAT — {(vat.data.payable_vat ?? 0) > 0 ? "Payable" : "Reclaimable"}
                  </p>
                  <p className={`mt-1 text-xl font-semibold ${(vat.data.payable_vat ?? 0) > 0 ? "text-red-900" : "text-emerald-900"}`}>
                    {vnd.format(Math.abs(vat.data.payable_vat ?? 0))}
                  </p>
                  <p className={`mt-1 text-xs ${(vat.data.payable_vat ?? 0) > 0 ? "text-red-600" : "text-emerald-600"}`}>
                    [40] field — {vat.data.declaration_deadline ? `Deadline: ${vat.data.declaration_deadline}` : "No deadline computed"}
                  </p>
                </div>
              </div>

              {/* Carry-forward & refund */}
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-lg border bg-white p-4">
                  <p className="text-sm text-slate-500">Carry-forward VAT [43]</p>
                  <p className="text-lg font-semibold">{vnd.format(vat.data.carry_forward_vat ?? 0)}</p>
                </div>
                <div className="rounded-lg border bg-white p-4">
                  <p className="text-sm text-slate-500">Refund Requested [42]</p>
                  <p className="text-lg font-semibold">{vnd.format(vat.data.refund_requested_vat ?? 0)}</p>
                </div>
              </div>

              {/* VAT by Rate Table */}
              <div className="rounded-lg border bg-white p-4">
                <h3 className="mb-3 font-semibold">VAT by Rate</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Rate</th>
                        <th className="py-2 pr-4 text-right">Input Base</th>
                        <th className="py-2 pr-4 text-right">Input VAT</th>
                        <th className="py-2 pr-4 text-right">Output Base</th>
                        <th className="py-2 text-right">Output VAT</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(vat.data.by_rate ?? [])
                        .filter((row: any) => row.input_amount || row.output_amount || row.input_vat || row.output_vat)
                        .map((row: any) => (
                          <tr key={row.rate} className="border-b last:border-0">
                            <td className="py-2 pr-4">{row.rate}%</td>
                            <td className="py-2 pr-4 text-right">{vnd.format(row.input_amount ?? 0)}</td>
                            <td className="py-2 pr-4 text-right">{vnd.format(row.input_vat ?? 0)}</td>
                            <td className="py-2 pr-4 text-right">{vnd.format(row.output_amount ?? 0)}</td>
                            <td className="py-2 text-right">{vnd.format(row.output_vat ?? 0)}</td>
                          </tr>
                        ))}
                      {vat.data.by_rate?.every((r: any) => !r.input_amount && !r.output_amount) && (
                        <tr>
                          <td className="py-8 text-center text-slate-500" colSpan={5}>
                            No VAT activity for this period.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Annex Totals */}
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-lg border bg-white p-4">
                  <h3 className="mb-3 font-semibold">Purchase Annex (01-1/GTGT)</h3>
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Count</dt>
                      <dd className="font-medium">{vat.data.purchase_annex?.totals?.count ?? 0}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Taxable Value</dt>
                      <dd className="font-medium">{vnd.format(vat.data.purchase_annex?.totals?.taxable_value ?? 0)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">VAT Amount</dt>
                      <dd className="font-medium">{vnd.format(vat.data.purchase_annex?.totals?.vat_amount ?? 0)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Total Amount</dt>
                      <dd className="font-medium">{vnd.format(vat.data.purchase_annex?.totals?.total_amount ?? 0)}</dd>
                    </div>
                  </dl>
                </div>

                <div className="rounded-lg border bg-white p-4">
                  <h3 className="mb-3 font-semibold">Sales Annex (01-2/GTGT)</h3>
                  <dl className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Count</dt>
                      <dd className="font-medium">{vat.data.sales_annex?.totals?.count ?? 0}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Taxable Value</dt>
                      <dd className="font-medium">{vnd.format(vat.data.sales_annex?.totals?.taxable_value ?? 0)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">VAT Amount</dt>
                      <dd className="font-medium">{vnd.format(vat.data.sales_annex?.totals?.vat_amount ?? 0)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Total Amount</dt>
                      <dd className="font-medium">{vnd.format(vat.data.sales_annex?.totals?.total_amount ?? 0)}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </>
          )}

          {!hasGenerated && (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center text-slate-500">
              <p>Select a period and click "Generate Report" to view the VAT summary.</p>
            </div>
          )}

          {hasGenerated && vat.isFetching && (
            <div className="rounded-lg border bg-white p-8 text-center text-slate-500">
              Loading...
            </div>
          )}
        </section>
        </main>
        </div>
    </ProtectedPage>
  );
}
