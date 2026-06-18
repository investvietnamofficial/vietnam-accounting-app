"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import * as Toast from "@radix-ui/react-toast";
import { ProtectedPage } from "@/components/protected-page";
import { Sidebar } from "@/components/sidebar";
import { useAuth } from "@/components/auth-provider";
import { useCompanySettings, useUpdateCompanySettings } from "@/hooks/useApi";
import type { CompanySettings } from "@/types";

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { data, isLoading } = useCompanySettings();
  const update = useUpdateCompanySettings();

  const [form, setForm] = useState<Partial<CompanySettings>>({});
  const [toastOpen, setToastOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState<{ type: "success" | "error"; text: string }>({
    type: "success",
    text: "",
  });

  useEffect(() => {
    if (data) {
      setForm({
        name: data.name ?? "",
        tax_code: data.tax_code ?? "",
        address: data.address ?? "",
        phone: data.phone ?? "",
        email: data.email ?? "",
        accounting_standard: data.accounting_standard ?? "TT200",
        vat_declaration_period: data.vat_declaration_period ?? "quarterly",
        fiscal_year_start_month: data.fiscal_year_start_month ?? 1,
      });
    }
  }, [data]);

  const handleSave = () => {
    update.mutate(form as Record<string, unknown>, {
      onSuccess: () => {
        setToastMsg({ type: "success", text: "Company settings saved successfully." });
        setToastOpen(true);
      },
      onError: () => {
        setToastMsg({ type: "error", text: "Failed to save settings. Please try again." });
        setToastOpen(true);
      },
    });
  };

  const field = (key: keyof CompanySettings, label: string, type = "text", placeholder = "") => (
    <label key={key} className="grid gap-1 text-sm">
      <span className="text-slate-600">{label}</span>
      <input
        className="h-10 rounded-md border px-3"
        type={type}
        value={String(form[key] ?? "")}
        placeholder={placeholder}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
      />
    </label>
  );

  return (
    <ProtectedPage>
      <Toast.Provider swipeDirection="right">
        <div className="flex min-h-screen bg-slate-50 text-slate-950">
          <Sidebar />
          <main className="flex-1">
            <header className="border-b bg-white">
              <div className="flex items-center justify-between px-6 py-4">
                <div>
                  <p className="text-sm text-slate-500">{user?.email}</p>
                  <h1 className="text-2xl font-semibold">Settings</h1>
                </div>
                <button className="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100" onClick={logout}>Sign out</button>
              </div>
            </header>

            <section className="max-w-2xl px-6 py-6">
            <h2 className="mb-4 text-lg font-semibold">Company Information</h2>

            {isLoading ? (
              <p className="text-center text-slate-500 py-12">Loading settings...</p>
            ) : (
              <div className="space-y-6">
                {/* Basic info */}
                <div className="rounded-lg border bg-white p-4 space-y-4">
                  <h3 className="font-medium text-slate-700">Company Details</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {field("name", "Company Name", "text", "Enter company name")}
                    {field("tax_code", "Tax Code (MST)", "text", "e.g. 0123456789")}
                    {field("address", "Address", "text", "Full business address")}
                    {field("phone", "Phone", "tel", "+84 ...")}
                    {field("email", "Email", "email", "company@example.com")}
                  </div>
                </div>

                {/* Accounting settings */}
                <div className="rounded-lg border bg-white p-4 space-y-4">
                  <h3 className="font-medium text-slate-700">Accounting Configuration</h3>

                  {/* Accounting Standard */}
                  <div className="space-y-2">
                    <p className="text-sm text-slate-600">Accounting Standard</p>
                    <div className="flex gap-4">
                      {(["TT200", "TT133"] as const).map((std) => (
                        <label key={std} className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="radio"
                            name="accounting_standard"
                            value={std}
                            checked={form.accounting_standard === std}
                            onChange={() => setForm((f) => ({ ...f, accounting_standard: std }))}
                            className="accent-emerald-700"
                          />
                          <span className="text-sm">{std === "TT200" ? "VAS / TT200" : "IFRS / TT133"}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* VAT Filing Period */}
                  <div className="space-y-2">
                    <p className="text-sm text-slate-600">VAT Filing Period</p>
                    <div className="flex gap-4">
                      {(["monthly", "quarterly"] as const).map((period) => (
                        <label key={period} className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="radio"
                            name="vat_declaration_period"
                            value={period}
                            checked={form.vat_declaration_period === period}
                            onChange={() => setForm((f) => ({ ...f, vat_declaration_period: period }))}
                            className="accent-emerald-700"
                          />
                          <span className="text-sm capitalize">{period}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Fiscal Year Start Month */}
                  <label className="grid gap-1 text-sm max-w-[200px]">
                    <span className="text-slate-600">Fiscal Year Start Month</span>
                    <select
                      className="h-10 rounded-md border px-3"
                      value={form.fiscal_year_start_month ?? 1}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, fiscal_year_start_month: Number(e.target.value) }))
                      }
                    >
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                        <option key={m} value={m}>
                          {new Date(2000, m - 1, 1).toLocaleString("en", { month: "long" })}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {/* Save Button */}
                <button
                  onClick={handleSave}
                  disabled={update.isPending}
                  className="inline-flex items-center gap-2 rounded-md bg-emerald-700 px-6 py-2.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
                >
                  <Save size={16} />
                  {update.isPending ? "Saving..." : "Save Settings"}
                </button>
              </div>
            )}
          </section>
          </main>
          </div>

        <Toast.Root
          className={`rounded-lg border p-4 shadow-lg ${
            toastMsg.type === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-red-200 bg-red-50 text-red-900"
          }`}
          open={toastOpen}
          onOpenChange={setToastOpen}
        >
          <Toast.Title className="font-medium">{toastMsg.text}</Toast.Title>
          <Toast.Description className="text-sm mt-1 opacity-80" />
          <Toast.Close className="absolute right-2 top-2 opacity-60 hover:opacity-100" />
        </Toast.Root>
        <Toast.Viewport className="fixed bottom-4 right-4 flex flex-col gap-2 w-[320px] z-50" />
      </Toast.Provider>
    </ProtectedPage>
  );
}
