"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import { useSalesInvoicesReport } from "@/hooks/useApi";

const vnd = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

const ITEMS_PER_PAGE = 50;

export default function SalesInvoicesPage() {
  const { user, logout } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [periodType, setPeriodType] = useState<"monthly" | "quarterly">("quarterly");
  const [period, setPeriod] = useState(Math.floor(now.getMonth() / 3) + 1);
  const [page, setPage] = useState(1);
  const [generated, setGenerated] = useState(false);

  const report = useSalesInvoicesReport(year, period, periodType);
  const items = report.data?.items ?? [];
  const total = items.length;
  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);
  const paginatedItems = items.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

  const handleGenerate = () => {
    report.refetch();
    setGenerated(true);
    setPage(1);
  };

  const periodLabel =
    periodType === "quarterly"
      ? `Q${period}/${year}`
      : `Month ${period}/${year}`;

  return (
    <ProtectedPage>
      <div className="flex min-h-screen bg-slate-50 text-slate-950">
        <Sidebar />
        <main className="flex-1">
          <header className="border-b bg-white">
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm text-slate-500">{user?.email}</p>
                <h1 className="text-2xl font-semibold">Sales Invoices Report</h1>
              </div>
              <button className="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
            </div>
          </header>
          <section className="px-6 py-6 space-y-4">
          {/* Period Selector */}
          <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-white p-4">
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
                  <option key={v} value={v}>{periodType === "quarterly" ? `Q${v}` : `Month ${v}`}</option>
                ))}
              </select>
            </label>
            <button
              onClick={handleGenerate}
              disabled={report.isFetching}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-emerald-700 px-4 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              <RefreshCw size={15} className={report.isFetching ? "animate-spin" : ""} />
              Generate
            </button>
            {generated && report.data && (
              <button
                className="ml-auto inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm hover:bg-slate-100"
              >
                <Download size={15} />
                Export Excel
              </button>
            )}
          </div>

          {/* Table */}
          {generated && (
            <div className="overflow-hidden rounded-lg border bg-white">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1200px] text-left text-sm">
                  <thead className="border-b bg-slate-100 text-slate-600">
                    <tr>
                      <th className="px-3 py-3">#</th>
                      <th className="px-3">Date</th>
                      <th className="px-3">Seller</th>
                      <th className="px-3">Seller MST</th>
                      <th className="px-3">Buyer</th>
                      <th className="px-3">Buyer MST</th>
                      <th className="px-3 text-right">Subtotal</th>
                      <th className="px-3 text-right">VAT Rate</th>
                      <th className="px-3 text-right">VAT Amount</th>
                      <th className="px-3 text-right">Total</th>
                      <th className="px-3">Verified</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.isFetching && (
                      <tr>
                        <td className="px-3 py-8 text-center text-slate-500" colSpan={11}>
                          Loading...
                        </td>
                      </tr>
                    )}
                    {!report.isFetching && paginatedItems.length === 0 && (
                      <tr>
                        <td className="px-3 py-8 text-center text-slate-500" colSpan={11}>
                          No sales invoices for {periodLabel}.
                        </td>
                      </tr>
                    )}
                    {paginatedItems.map((item: any, idx: number) => (
                      <tr key={item.id ?? idx} className="border-b last:border-0">
                        <td className="px-3 py-2">{item.stt ?? idx + 1}</td>
                        <td className="px-3 py-2">
                          {item.invoice_date
                            ? new Date(item.invoice_date).toLocaleDateString("vi-VN")
                            : "-"}
                        </td>
                        <td className="px-3 py-2 max-w-[180px] truncate">{item.seller_name ?? "-"}</td>
                        <td className="px-3 py-2">{item.seller_tax_code ?? "-"}</td>
                        <td className="px-3 py-2 max-w-[180px] truncate">{item.buyer_name ?? "-"}</td>
                        <td className="px-3 py-2">{item.buyer_tax_code ?? "-"}</td>
                        <td className="px-3 py-2 text-right">{vnd.format(item.subtotal_amount ?? 0)}</td>
                        <td className="px-3 py-2 text-right">{item.vat_rate}%</td>
                        <td className="px-3 py-2 text-right">{vnd.format(item.vat_amount ?? 0)}</td>
                        <td className="px-3 py-2 text-right font-medium">{vnd.format(item.total_amount ?? 0)}</td>
                        <td className="px-3 py-2">
                          <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs ${
                            item.einvoice_verified
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-amber-100 text-amber-700"
                          }`}>
                            {item.einvoice_verified ? "Yes" : "No"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between border-t px-4 py-3">
                  <p className="text-sm text-slate-500">
                    Showing {(page - 1) * ITEMS_PER_PAGE + 1}–{Math.min(page * ITEMS_PER_PAGE, total)} of {total} invoices
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                      className="rounded-md border bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                      className="rounded-md border bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {!generated && (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center text-slate-500">
              Select a period and click "Generate" to view sales invoices.
            </div>
          )}
        </section>
        </main>
        </div>
    </ProtectedPage>
  );
}
