"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [form, setForm] = useState({
    fullName: "",
    companyName: "",
    companyTaxCode: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await register(form);
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to create account");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Create tenant" subtitle="Provision your company and initial admin account in one step.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Field label="Full name" tooltip="Enter the legal or preferred name of the initial admin user." value={form.fullName} onChange={(value) => setForm({ ...form, fullName: value })} />
        <Field label="Company name" tooltip="Use the registered Vietnamese company name that owns this workspace." value={form.companyName} onChange={(value) => setForm({ ...form, companyName: value })} />
        <Field label="Company tax code" tooltip="Enter the 10-digit or 13-digit MST used for tax reporting and invoice matching." value={form.companyTaxCode} onChange={(value) => setForm({ ...form, companyTaxCode: value })} />
        <Field label="Work email" tooltip="This email becomes the first admin login for the tenant." type="email" value={form.email} onChange={(value) => setForm({ ...form, email: value })} />
        <Field
          label="Password"
          tooltip="Choose a strong password for the first admin user."
          type="password"
          helper="Minimum 12 characters with upper, lower, and number."
          value={form.password}
          onChange={(value) => setForm({ ...form, password: value })}
        />
        {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <button
          disabled={isSubmitting}
          title="Create the company tenant and sign in as its initial admin user."
          className="w-full rounded-md bg-emerald-700 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {isSubmitting ? "Creating account..." : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-sm text-slate-600">
        Already have access? <Link href="/auth/login" title="Go back to the sign-in form for an existing account." className="text-emerald-700 hover:underline">Sign in</Link>
      </p>
    </AuthLayout>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  helper,
  tooltip,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  helper?: string;
  tooltip?: string;
}) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <input
        required
        type={type}
        value={value}
        title={tooltip ?? `Enter ${label.toLowerCase()}.`}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 rounded-md border border-slate-300 px-3 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
      />
      {helper && <span className="text-xs text-slate-500">{helper}</span>}
    </label>
  );
}
