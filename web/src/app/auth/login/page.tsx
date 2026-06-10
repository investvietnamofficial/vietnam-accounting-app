"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login({ email, password });
      const next =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("next")
          : null;
      router.replace(next || "/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to sign in");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Access your company workspace with your own account credentials.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Field
          label="Work email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          tooltip="Use the email address tied to your company account."
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          tooltip="Enter your current account password. Passwords are case-sensitive."
        />
        {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <button
          disabled={isSubmitting}
          title="Submit your work email and password to open the company dashboard."
          className="w-full rounded-md bg-emerald-700 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
      <div className="mt-6 flex items-center justify-between text-sm">
        <Link
          href="/auth/forgot-password"
          title="Open the password-reset flow and generate a reset token for this email address."
          className="text-emerald-700 hover:underline"
        >
          Forgot password?
        </Link>
        <Link
          href="/auth/register"
          title="Create a new tenant and the first admin account for that company."
          className="text-slate-600 hover:underline"
        >
          Create account
        </Link>
      </div>
    </AuthLayout>
  );
}

function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
  tooltip,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
  tooltip?: string;
}) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <input
        required
        type={type}
        value={value}
        autoComplete={autoComplete}
        title={tooltip ?? `Enter ${label.toLowerCase()}.`}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 rounded-md border border-slate-300 px-3 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
      />
    </label>
  );
}
