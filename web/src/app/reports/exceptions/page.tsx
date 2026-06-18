"use client";

import Link from "next/link";
import { useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Copy,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import { useExceptionsReport } from "@/hooks/useApi";

const ISSUE_CONFIG: Record<
  string,
  { label: string; icon: React.ReactNode; color: string; bgColor: string }
> = {
  missing_seller_mst: {
    label: "Missing Seller MST",
    icon: <AlertTriangle size={18} />,
    color: "text-yellow-700",
    bgColor: "bg-yellow-50 border-yellow-200",
  },
  duplicate_invoice: {
    label: "Duplicate Invoices",
    icon: <Copy size={18} />,
    color: "text-orange-700",
    bgColor: "bg-orange-50 border-orange-200",
  },
  low_confidence: {
    label: "Low Confidence Extraction",
    icon: <AlertCircle size={18} />,
    color: "text-amber-700",
    bgColor: "bg-amber-50 border-amber-200",
  },
  vat_mismatch: {
    label: "VAT Mismatch",
    icon: <AlertCircle size={18} />,
    color: "text-red-700",
    bgColor: "bg-red-50 border-red-200",
  },
};

export default function ExceptionsPage() {
  const { user, logout } = useAuth();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [periodType, setPeriodType] = useState<"monthly" | "quarterly">("quarterly");
  const [period, setPeriod] = useState(Math.floor(now.getMonth() / 3) + 1);
  const [generated, setGenerated] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const report = useExceptionsReport(year, period, periodType);

  const handleGenerate = () => {
    report.refetch();
    setGenerated(true);
  };

  const toggleExpand = (type: string) =>
    setExpanded((e) => ({ ...e, [type]: !e[type] }));

  const totalIssues = report.data?.total_issues ?? 0;

  return (
    <ProtectedPage>
      <div className="flex min-h-screen bg-slate-50 text-slate-950">
        <Sidebar />
        <main className="flex-1">
          <header className="border-b bg-white">
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm text-slate-500">{user?.email}</p>
                <h1 className="text-2xl font-semibold">Exceptions Report</h1>
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
          </div>

          {/* Summary */}
          {generated && report.data && (
            <div className="flex items-center gap-3 rounded-lg border bg-white p-4">
              <span className={`rounded-full px-3 py-1 text-sm font-medium ${
                totalIssues === 0
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-amber-100 text-amber-700"
              }`}>
                {totalIssues === 0 ? "No issues found" : `${totalIssues} issue${totalIssues !== 1 ? "s" : ""} found`}
              </span>
              <span className="text-sm text-slate-500">
                {periodType === "quarterly"
                  ? `Q${period}/${year}`
                  : `Month ${period}/${year}`}
              </span>
            </div>
          )}

          {/* Issues */}
          {generated && (
            <div className="space-y-3">
              {report.isFetching && (
                <p className="text-center text-slate-500 py-8">Analyzing invoices...</p>
              )}
              {!report.isFetching && report.data?.issues?.length === 0 && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-8 text-center">
                  <p className="font-medium text-emerald-700">No exceptions found</p>
                  <p className="mt-1 text-sm text-emerald-600">
                    All invoices passed the validation checks.
                  </p>
                </div>
              )}
              {!report.isFetching && report.data?.issues?.map((issue: any) => {
                const cfg =
                  ISSUE_CONFIG[issue.type] ?? {
                    label: issue.type,
                    icon: <AlertCircle size={18} />,
                    color: "text-slate-700",
                    bgColor: "bg-slate-50 border-slate-200",
                  };
                const isExpanded = expanded[issue.type] ?? false;

                return (
                  <div
                    key={issue.type}
                    className={`rounded-lg border p-4 ${cfg.bgColor}`}
                  >
                    <div
                      className="flex items-center justify-between cursor-pointer"
                      onClick={() => toggleExpand(issue.type)}
                    >
                      <div className="flex items-center gap-3">
                        <span className={cfg.color}>{cfg.icon}</span>
                        <div>
                          <p className={`font-medium ${cfg.color}`}>{cfg.label}</p>
                          <p className="text-sm text-slate-600">{issue.message}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium bg-white ${cfg.color}`}>
                          {issue.count} invoice{issue.count !== 1 ? "s" : ""}
                        </span>
                        <button className="text-slate-400 hover:text-slate-600">
                          {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </button>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="mt-3 border-t pt-3">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-slate-500">
                              <th className="pb-2">Invoice #</th>
                              <th className="pb-2">Date</th>
                              <th className="pb-2">Seller</th>
                              <th className="pb-2">VAT Rate</th>
                              <th className="pb-2 text-right">Total</th>
                              <th className="pb-2"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {issue.invoice_ids.map((id: string) => {
                              // We don't have invoice details here — link to invoice detail
                              return (
                                <tr key={id} className="border-t">
                                  <td className="py-2 font-mono text-xs">{id.slice(0, 8)}...</td>
                                  <td className="py-2 text-slate-500">—</td>
                                  <td className="py-2 text-slate-500">—</td>
                                  <td className="py-2 text-slate-500">—</td>
                                  <td className="py-2 text-right text-slate-500">—</td>
                                  <td className="py-2 text-right">
                                    <Link
                                      href={`/invoices?id=${id}`}
                                      className="text-xs text-emerald-700 hover:underline"
                                    >
                                      View
                                    </Link>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {!generated && (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-12 text-center text-slate-500">
              Select a period and click "Generate" to run exception analysis.
            </div>
          )}
        </section>
        </main>
        </div>
    </ProtectedPage>
  );
}
