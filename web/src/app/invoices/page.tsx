"use client";

import Link from "next/link";
import { useState } from "react";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  X,
} from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import { useFilteredInvoices, useVerifyEInvoice } from "@/hooks/useApi";
import type { Invoice } from "@/types";

const vnd = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

const VAT_RATES = ["all", "0", "5", "8", "10", "exempt", "na"];
const STATUS_TABS = ["all", "verified", "pending", "failed"] as const;

export default function InvoicesPage() {
  const { user, logout } = useAuth();

  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [vatRate, setVatRate] = useState("all");
  const [seller, setSeller] = useState("");
  const [statusTab, setStatusTab] = useState<string>("all");
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  const params = {
    page,
    page_size: 20,
    ...(dateFrom && { date_from: dateFrom }),
    ...(dateTo && { date_to: dateTo }),
    ...(vatRate !== "all" && { vat_rate: vatRate }),
    ...(seller && { seller }),
  };

  const { data, isLoading, refetch, isFetching } = useFilteredInvoices(params);
  const invoices: Invoice[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 20);

  // Client-side status filter (since API uses einvoice_verified flag)
  const filteredInvoices =
    statusTab === "all"
      ? invoices
      : invoices.filter((inv) =>
          statusTab === "verified"
            ? inv.einvoice_verified
            : statusTab === "pending"
            ? !inv.einvoice_verified
            : false
        );

  const clearFilters = () => {
    setDateFrom("");
    setDateTo("");
    setVatRate("all");
    setSeller("");
    setStatusTab("all");
    setPage(1);
  };

  const hasFilters =
    dateFrom || dateTo || vatRate !== "all" || seller || statusTab !== "all";

  return (
    <ProtectedPage>
      <div className="flex min-h-screen bg-slate-50 text-slate-950">
        <Sidebar />
        <main className="flex-1">
          <header className="border-b bg-white">
            <div className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="text-sm text-slate-500">{user?.email}</p>
                <h1 className="text-2xl font-semibold">Invoices</h1>
              </div>
              <button className="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
            </div>
          </header>

          <section className="px-6 py-6 space-y-4">
          {/* Filter Bar */}
          <div className="rounded-lg border bg-white p-4 space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              {/* Date From */}
              <label className="grid gap-1 text-sm">
                <span className="text-slate-500">Date from</span>
                <input
                  className="h-9 rounded-md border px-3"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => {
                    setDateFrom(e.target.value);
                    setPage(1);
                  }}
                />
              </label>

              {/* Date To */}
              <label className="grid gap-1 text-sm">
                <span className="text-slate-500">Date to</span>
                <input
                  className="h-9 rounded-md border px-3"
                  type="date"
                  value={dateTo}
                  onChange={(e) => {
                    setDateTo(e.target.value);
                    setPage(1);
                  }}
                />
              </label>

              {/* VAT Rate */}
              <label className="grid gap-1 text-sm">
                <span className="text-slate-500">VAT Rate</span>
                <select
                  className="h-9 rounded-md border px-3"
                  value={vatRate}
                  onChange={(e) => {
                    setVatRate(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="all">All rates</option>
                  <option value="0">0%</option>
                  <option value="5">5%</option>
                  <option value="8">8%</option>
                  <option value="10">10%</option>
                  <option value="exempt">Exempt</option>
                  <option value="na">N/A</option>
                </select>
              </label>

              {/* Seller search */}
              <label className="grid gap-1 text-sm flex-1 min-w-[160px]">
                <span className="text-slate-500">Seller</span>
                <input
                  className="h-9 rounded-md border px-3"
                  type="text"
                  placeholder="Search seller name..."
                  value={seller}
                  onChange={(e) => {
                    setSeller(e.target.value);
                    setPage(1);
                  }}
                />
              </label>

              {/* Refresh */}
              <button
                onClick={() => refetch()}
                disabled={isFetching}
                className="inline-flex h-9 items-center gap-1.5 rounded-md border bg-white px-3 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
                Refresh
              </button>

              {/* Clear */}
              {hasFilters && (
                <button
                  onClick={clearFilters}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-3 text-sm text-red-600 hover:bg-red-100"
                >
                  <X size={14} />
                  Clear
                </button>
              )}
            </div>

            {/* Status Tabs */}
            <div className="flex items-center gap-1 border-t pt-3">
              {STATUS_TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => {
                    setStatusTab(tab);
                    setPage(1);
                  }}
                  className={`rounded-md px-3 py-1.5 text-sm capitalize ${
                    statusTab === tab
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {tab}
                  {tab === "verified" &&
                    ` (${invoices.filter((i) => i.einvoice_verified).length})`}
                  {tab === "pending" &&
                    ` (${invoices.filter((i) => !i.einvoice_verified).length})`}
                </button>
              ))}
            </div>
          </div>

          {/* Table */}
          <div className="overflow-hidden rounded-lg border bg-white">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1000px] text-left text-sm">
                <thead className="border-b bg-slate-100 text-slate-600">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-3">Invoice #</th>
                    <th className="px-3">Seller</th>
                    <th className="px-3">Buyer</th>
                    <th className="px-3 text-right">Amount</th>
                    <th className="px-3 text-right">VAT</th>
                    <th className="px-3">Status</th>
                    <th className="px-3 text-right">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading && (
                    <tr>
                      <td
                        className="px-4 py-8 text-center text-slate-500"
                        colSpan={8}
                      >
                        Loading invoices...
                      </td>
                    </tr>
                  )}
                  {!isLoading && filteredInvoices.length === 0 && (
                    <tr>
                      <td
                        className="px-4 py-8 text-center text-slate-500"
                        colSpan={8}
                      >
                        {hasFilters
                          ? "No invoices match your filters."
                          : "No invoices yet. Upload a document to get started."}
                      </td>
                    </tr>
                  )}
                  {filteredInvoices.map((invoice) => (
                    <InvoiceRow
                      key={invoice.id}
                      invoice={invoice}
                      onClick={() => setSelectedInvoice(invoice)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t px-4 py-3">
                <p className="text-sm text-slate-500">
                  Page {page} of {totalPages} — {total} invoices
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="inline-flex items-center gap-1 rounded-md border bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
                  >
                    <ChevronLeft size={14} />
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="inline-flex items-center gap-1 rounded-md border bg-white px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
                  >
                    Next
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Invoice Detail Modal */}
        {selectedInvoice && (
          <InvoiceDetailModal
            invoice={selectedInvoice}
            onClose={() => setSelectedInvoice(null)}
          />
        )}
        </main>
        </div>
    </ProtectedPage>
  );
}

function InvoiceRow({
  invoice,
  onClick,
}: {
  invoice: Invoice;
  onClick: () => void;
}) {
  const verify = useVerifyEInvoice(invoice.id);
  const isVerified = invoice.einvoice_verified;

  return (
    <tr
      className="cursor-pointer border-b last:border-0 hover:bg-slate-50"
      onClick={onClick}
    >
      <td className="px-4 py-3">
        {invoice.invoice_date
          ? new Date(invoice.invoice_date).toLocaleDateString("vi-VN")
          : "-"}
      </td>
      <td className="px-3">
        {invoice.invoice_series ?? "-"} / {invoice.invoice_number ?? "-"}
      </td>
      <td className="px-3 max-w-[200px] truncate">
        {invoice.seller_name ?? "-"}
      </td>
      <td className="px-3 max-w-[200px] truncate">
        {invoice.buyer_name ?? "-"}
      </td>
      <td className="px-3 text-right font-medium">
        {vnd.format(invoice.total_amount ?? 0)}
      </td>
      <td className="px-3 text-right">
        {invoice.vat_rate}% · {vnd.format(invoice.vat_amount ?? 0)}
      </td>
      <td className="px-3">
        <span
          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${
            isVerified
              ? "bg-emerald-100 text-emerald-800"
              : "bg-amber-100 text-amber-800"
          }`}
        >
          {isVerified && <CheckCircle2 size={12} />}
          {isVerified ? "Verified" : "Pending"}
        </span>
      </td>
      <td className="px-3 text-right text-slate-500">
        {invoice.einvoice_verified_at ? (
          <span className="text-xs text-slate-400">—</span>
        ) : (
          <span className="text-xs text-slate-500">—</span>
        )}
      </td>
    </tr>
  );
}

function InvoiceDetailModal({
  invoice,
  onClose,
}: {
  invoice: Invoice;
  onClose: () => void;
}) {
  const verify = useVerifyEInvoice(invoice.id);

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content className="fixed left-1/2 top-1/2 max-h-[90vh] w-[600px] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">
              Invoice Detail
            </Dialog.Title>
            <Dialog.Close className="text-slate-400 hover:text-slate-600">
              <X size={18} />
            </Dialog.Close>
          </div>

          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <FieldRow label="Invoice Series" value={invoice.invoice_series ?? "-"} />
              <FieldRow label="Invoice Number" value={invoice.invoice_number ?? "-"} />
              <FieldRow label="Date" value={invoice.invoice_date ? new Date(invoice.invoice_date).toLocaleDateString("vi-VN") : "-"} />
              <FieldRow label="Type" value={invoice.invoice_type ?? "-"} />
            </div>

            <div className="border-t pt-3">
              <p className="mb-2 font-medium text-slate-500">Seller</p>
              <div className="grid grid-cols-2 gap-2">
                <FieldRow label="Name" value={invoice.seller_name ?? "-"} />
                <FieldRow label="MST" value={invoice.seller_tax_code ?? "-"} />
                <div className="col-span-2">
                  <FieldRow label="Address" value={invoice.seller_address ?? "-"} />
                </div>
              </div>
            </div>

            <div className="border-t pt-3">
              <p className="mb-2 font-medium text-slate-500">Buyer</p>
              <div className="grid grid-cols-2 gap-2">
                <FieldRow label="Name" value={invoice.buyer_name ?? "-"} />
                <FieldRow label="MST" value={invoice.buyer_tax_code ?? "-"} />
                <div className="col-span-2">
                  <FieldRow label="Address" value={invoice.buyer_address ?? "-"} />
                </div>
              </div>
            </div>

            <div className="border-t pt-3">
              <div className="grid grid-cols-2 gap-2">
                <FieldRow label="Subtotal" value={vnd.format(invoice.subtotal_amount ?? 0)} />
                <FieldRow label="VAT Rate" value={`${invoice.vat_rate}%`} />
                <FieldRow label="VAT Amount" value={vnd.format(invoice.vat_amount ?? 0)} />
                <FieldRow label="Total" value={vnd.format(invoice.total_amount ?? 0)} strong />
                <FieldRow label="E-invoice Code" value={invoice.einvoice_code ?? "-"} />
                <FieldRow
                  label="Verified"
                  value={invoice.einvoice_verified ? "Yes" : "No"}
                  valueColor={invoice.einvoice_verified ? "text-emerald-600" : "text-amber-600"}
                />
              </div>
            </div>

            {invoice.notes && (
              <div className="border-t pt-3">
                <FieldRow label="Notes" value={invoice.notes} />
              </div>
            )}
          </div>

          <div className="mt-4 flex justify-end gap-3">
            <button
              onClick={onClose}
              className="rounded-md border px-4 py-2 text-sm hover:bg-slate-100"
            >
              Close
            </button>
            {!invoice.einvoice_verified && (
              <button
                onClick={() => verify.mutate()}
                disabled={verify.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                <CheckCircle2 size={14} />
                {verify.isPending ? "Verifying..." : "Mark as Verified"}
              </button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FieldRow({
  label,
  value,
  strong = false,
  valueColor = "text-slate-900",
}: {
  label: string;
  value: string;
  strong?: boolean;
  valueColor?: string;
}) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`${valueColor} ${strong ? "font-semibold" : ""}`}>{value}</p>
    </div>
  );
}
