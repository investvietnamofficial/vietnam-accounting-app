"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";

export default function ResetPasswordPage() {
  const router = useRouter();
  const { resetPassword } = useAuth();
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await resetPassword(resetToken, newPassword);
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Unable to reset password");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout title="Set new password" subtitle="Submit the reset token and choose a stronger password.">
      <form className="space-y-4" onSubmit={handleSubmit}>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-slate-700">Reset token</span>
          <textarea
            required
            value={resetToken}
            title="Paste the full reset token you generated from the previous step."
            aria-label="Reset token"
            onChange={(event) => setResetToken(event.target.value)}
            className="min-h-28 rounded-md border border-slate-300 px-3 py-3 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
          />
        </label>
        <label className="grid gap-2 text-sm">
          <span className="font-medium text-slate-700">New password</span>
          <input
            required
            type="password"
            value={newPassword}
            title="Set a new password that meets the minimum strength policy."
            aria-label="New password"
            onChange={(event) => setNewPassword(event.target.value)}
            className="h-11 rounded-md border border-slate-300 px-3 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
          />
          <span className="text-xs text-slate-500">Minimum 12 characters with upper, lower, and number.</span>
        </label>
        {error && <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
        <button
          disabled={isSubmitting}
          title="Submit the token and replace the current password with the new one."
          className="w-full rounded-md bg-emerald-700 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {isSubmitting ? "Updating..." : "Update password"}
        </button>
      </form>
      <p className="mt-6 text-sm text-slate-600">
        Back to <Link href="/auth/login" title="Return to the main sign-in form." className="text-emerald-700 hover:underline">sign in</Link>
      </p>
    </AuthLayout>
  );
}
