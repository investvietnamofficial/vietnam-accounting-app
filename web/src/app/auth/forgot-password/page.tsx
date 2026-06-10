"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setResetToken(null);
    setIsSubmitting(true);
    try {
      const response = await forgotPassword(email);
      setMessage(response.message);
      setResetToken(response.reset_token ?? null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to start password reset");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Reset password" subtitle="Generate a reset token for your account.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-slate-700">Work email</span>
          <input
            required
            type="email"
            value={email}
            title="Enter the email address for the account that needs a password reset token."
            aria-label="Work email"
            onChange={(event) => setEmail(event.target.value)}
            className="h-11 rounded-md border border-slate-300 px-3 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
          />
        </label>
        {message && <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p>}
        {resetToken && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Development reset token: <code className="break-all">{resetToken}</code>
          </div>
        )}
        {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <button
          disabled={isSubmitting}
          title="Generate a password reset token. In development the token is shown on screen."
          className="w-full rounded-md bg-emerald-700 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {isSubmitting ? "Generating..." : "Generate reset token"}
        </button>
      </form>
      <p className="mt-6 text-sm text-slate-600">
        Have a token already? <Link href="/auth/reset-password" title="Open the form where you can paste a reset token and choose a new password." className="text-emerald-700 hover:underline">Reset password</Link>
      </p>
    </AuthLayout>
  );
}
