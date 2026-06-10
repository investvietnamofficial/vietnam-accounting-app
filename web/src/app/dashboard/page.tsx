"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useRef } from "react";
import { FileUp, ReceiptText, RefreshCw, ShieldCheck, TrendingUp } from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { useAuth } from "@/components/auth-provider";
import { useDocuments, useInvoices, useUploadDocument, useVATSummary } from "@/hooks/useApi";

const vnd = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });

function currentQuarter() {
  return Math.floor(new Date().getMonth() / 3) + 1;
}

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const year = new Date().getFullYear();
  const period = currentQuarter();
  const fileInput = useRef<HTMLInputElement>(null);
  const documents = useDocuments({ page: 1 });
  const invoices = useInvoices({ page: 1 });
  const vat = useVATSummary(year, period, "quarterly");
  const upload = useUploadDocument();

  const invoiceItems = invoices.data?.items ?? [];
  const documentItems = documents.data?.items ?? [];
  const pendingCount = documentItems.filter((doc: any) => ["pending", "processing"].includes(doc.status)).length;
  const totalInvoiceValue = useMemo(
    () => invoiceItems.reduce((sum: number, item: any) => sum + (item.total_amount ?? 0), 0),
    [invoiceItems]
  );

  return (
    <ProtectedPage>
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm text-slate-500">{user?.email}</p>
            <h1 className="text-2xl font-semibold">Compliance Workspace</h1>
          </div>
          <nav className="flex items-center gap-2 text-sm">
            <Link title="Open the dashboard overview for uploads, invoice activity, and VAT status." className="rounded-md bg-slate-900 px-3 py-2 text-white" href="/dashboard">Dashboard</Link>
            <Link title="Browse extracted invoices, amounts, and review status." className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100" href="/invoices">Invoices</Link>
            <Link title="Open VAT and CIT reports, declaration inputs, and exports." className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100" href="/reports">Reports</Link>
            <button title="Sign out of the current tenant session." className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-6">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Quarter {period}, {year}</h2>
            <p className="text-sm text-slate-500">Tenant: {user?.company_id ?? "Unassigned"}</p>
          </div>
          <input
            ref={fileInput}
            className="hidden"
            type="file"
            accept="image/*,application/pdf"
            title="Choose an invoice image or PDF to send through OCR and extraction."
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload.mutate({ file, docType: "invoice_vat" });
              event.currentTarget.value = "";
            }}
          />
          <button
            onClick={() => fileInput.current?.click()}
            title="Pick a VAT invoice image or PDF and start document processing."
            className="inline-flex items-center gap-2 rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800"
          >
            <FileUp size={16} /> Upload document
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Metric icon={<ReceiptText size={18} />} label="Invoices" tooltip="Total extracted invoice records currently available in the workspace." value={String(invoices.data?.total ?? invoiceItems.length)} />
          <Metric icon={<TrendingUp size={18} />} label="Invoice value" tooltip="Combined gross value of the invoices loaded on this page." value={vnd.format(totalInvoiceValue)} />
          <Metric icon={<ShieldCheck size={18} />} label="Net VAT" tooltip="Current net VAT position for the active quarter. Negative means input VAT exceeds output VAT." value={vnd.format(vat.data?.net_vat ?? 0)} />
          <Metric icon={<RefreshCw size={18} />} label="Pending docs" tooltip="Documents still waiting for OCR or extraction to complete." value={String(pendingCount)} />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <section className="rounded-lg border bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-semibold">Recent invoices</h3>
              <Link title="Open the full invoice register with review actions." className="text-sm text-emerald-700 hover:underline" href="/invoices">View all</Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b text-slate-500">
                  <tr>
                    <th title="Invoice issuance date extracted from the document." className="py-2">Date</th>
                    <th title="Invoice series and invoice number." >Invoice</th>
                    <th title="Seller legal entity name detected during extraction." >Seller</th>
                    <th title="Gross invoice total including VAT." className="text-right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {invoiceItems.slice(0, 6).map((invoice: any) => (
                    <tr key={invoice.id} className="border-b last:border-0">
                      <td className="py-2">{invoice.invoice_date?.slice(0, 10) ?? "-"}</td>
                      <td>{invoice.invoice_series ?? "-"} {invoice.invoice_number ?? ""}</td>
                      <td>{invoice.seller_name ?? "Unreviewed"}</td>
                      <td className="text-right">{vnd.format(invoice.total_amount ?? 0)}</td>
                    </tr>
                  ))}
                  {!invoiceItems.length && (
                    <tr><td className="py-8 text-center text-slate-500" colSpan={4}>Upload a document to create the first invoice.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-lg border bg-white p-4">
            <h3 className="mb-3 font-semibold">VAT by rate</h3>
            <div className="space-y-3">
              {(vat.data?.by_rate ?? []).filter((row: any) => row.input_vat || row.output_vat).map((row: any) => (
                <div key={row.rate} title={`VAT position for the ${row.rate}% rate bucket in the current quarter.`} className="rounded-md border p-3">
                  <div className="mb-1 flex justify-between text-sm font-medium">
                    <span>{row.rate}% VAT</span>
                    <span>{vnd.format((row.output_vat ?? 0) - (row.input_vat ?? 0))}</span>
                  </div>
                  <p className="text-xs text-slate-500">Input {vnd.format(row.input_vat ?? 0)} · Output {vnd.format(row.output_vat ?? 0)}</p>
                </div>
              ))}
              {vat.isLoading && <p className="text-sm text-slate-500">Loading VAT position...</p>}
              {!vat.isLoading && !(vat.data?.by_rate ?? []).some((row: any) => row.input_vat || row.output_vat) && (
                <p className="text-sm text-slate-500">No VAT activity for this period yet.</p>
              )}
            </div>
          </section>
        </div>
      </section>
    </main>
    </ProtectedPage>
  );
}

function Metric({ icon, label, value, tooltip }: { icon: ReactNode; label: string; value: string; tooltip: string }) {
  return (
    <div title={tooltip} className="rounded-lg border bg-white p-4">
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-slate-100 text-slate-700">{icon}</div>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}
