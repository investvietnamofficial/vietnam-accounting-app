"use client";

import Link from "next/link";
import { CheckCircle2, RefreshCw } from "lucide-react";
import { ProtectedPage } from "@/components/protected-page";
import { useAuth } from "@/components/auth-provider";
import { useInvoices, useVerifyEInvoice } from "@/hooks/useApi";

const vnd = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });

export default function InvoicesPage() {
  const { user, logout } = useAuth();
  const { data, isLoading, refetch } = useInvoices({ page: 1 });
  const invoices = data?.items ?? [];

  return (
    <ProtectedPage>
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm text-slate-500">{user?.email}</p>
            <h1 className="text-2xl font-semibold">Invoices</h1>
          </div>
          <nav className="flex items-center gap-2 text-sm">
            <Link title="Return to the dashboard overview and upload actions." className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100" href="/dashboard">Dashboard</Link>
            <Link title="Stay on the invoice register and review extracted records." className="rounded-md bg-slate-900 px-3 py-2 text-white" href="/invoices">Invoices</Link>
            <Link title="Open tax reports and declaration exports." className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100" href="/reports">Reports</Link>
            <button title="Sign out of the current session." className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Extracted invoice register</h2>
            <p className="text-sm text-slate-500">Rows are created by the upload/OCR pipeline and should be reviewed before filing.</p>
          </div>
          <button
            onClick={() => refetch()}
            title="Reload the invoice register from the API."
            className="inline-flex items-center gap-2 rounded-md border bg-white px-3 py-2 text-sm hover:bg-slate-100"
          >
            <RefreshCw size={15} /> Refresh
          </button>
        </div>

        <div className="overflow-hidden rounded-lg border bg-white">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="border-b bg-slate-100 text-slate-600">
                <tr>
                  <th title="Invoice issuance date extracted from the uploaded document." className="px-4 py-3">Date</th>
                  <th title="Invoice series and invoice number." >Series / No.</th>
                  <th title="Seller legal entity name." >Seller</th>
                  <th title="Seller MST used for GDT validation and tax matching." >Seller MST</th>
                  <th title="Buyer legal entity name." >Buyer</th>
                  <th title="Subtotal before VAT." className="text-right">Subtotal</th>
                  <th title="Applied VAT rate and VAT amount." className="text-right">VAT</th>
                  <th title="Gross invoice total including VAT." className="text-right">Total</th>
                  <th title="Review state inside this workspace." >Status</th>
                  <th title="Available review action for this row." className="pr-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && (
                  <tr><td className="px-4 py-8 text-center text-slate-500" colSpan={10}>Loading invoices...</td></tr>
                )}
                {!isLoading && !invoices.length && (
                  <tr><td className="px-4 py-8 text-center text-slate-500" colSpan={10}>No invoices yet. Upload from the dashboard or mobile scanner.</td></tr>
                )}
                {invoices.map((invoice: any) => (
                  <InvoiceRow key={invoice.id} invoice={invoice} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
    </ProtectedPage>
  );
}

function InvoiceRow({ invoice }: { invoice: any }) {
  const verify = useVerifyEInvoice(invoice.id);
  return (
    <tr className="border-b last:border-0">
      <td className="px-4 py-3">{invoice.invoice_date?.slice(0, 10) ?? "-"}</td>
      <td>{invoice.invoice_series ?? "-"} / {invoice.invoice_number ?? "-"}</td>
      <td className="max-w-[220px] truncate">{invoice.seller_name ?? "-"}</td>
      <td>{invoice.seller_tax_code ?? "-"}</td>
      <td className="max-w-[220px] truncate">{invoice.buyer_name ?? "-"}</td>
      <td className="text-right">{vnd.format(invoice.subtotal_amount ?? 0)}</td>
      <td className="text-right">{invoice.vat_rate}% · {vnd.format(invoice.vat_amount ?? 0)}</td>
      <td className="text-right font-medium">{vnd.format(invoice.total_amount ?? 0)}</td>
      <td>
        <span title={invoice.einvoice_verified ? "This invoice has already been marked reviewed in the workspace." : "This invoice still needs operator review."} className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${
          invoice.einvoice_verified ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
        }`}>
          {invoice.einvoice_verified && <CheckCircle2 size={13} />}
          {invoice.einvoice_verified ? "Reviewed" : "Needs review"}
        </span>
      </td>
      <td className="pr-4 text-right">
        <button
          onClick={() => verify.mutate()}
          disabled={invoice.einvoice_verified || verify.isPending}
          title={invoice.einvoice_verified ? "This invoice is already reviewed, so no further action is needed." : "Mark this invoice as reviewed after checking the extracted values."}
          className="rounded-md border px-3 py-1.5 text-xs hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Mark reviewed
        </button>
      </td>
    </tr>
  );
}
