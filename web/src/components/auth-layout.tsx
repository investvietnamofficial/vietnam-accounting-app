"use client";

import Link from "next/link";

export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#d1fae5,_#f8fafc_40%,_#e2e8f0)] px-4 py-10 text-slate-950">
      <div className="mx-auto grid max-w-5xl gap-10 lg:grid-cols-[1fr_420px]">
        <section className="hidden rounded-3xl border border-white/60 bg-slate-900 p-10 text-slate-100 shadow-2xl lg:block">
          <p className="text-sm uppercase tracking-[0.25em] text-emerald-300">VN Accounting</p>
          <h1 className="mt-6 text-4xl font-semibold leading-tight">Tenant-safe accounting operations for Vietnam teams.</h1>
          <p className="mt-4 max-w-md text-sm leading-6 text-slate-300">
            Keep invoice processing, tax reporting, and company data isolated per tenant with authenticated access.
          </p>
          <div className="mt-10 space-y-3 text-sm text-slate-300">
            <p>Separate tenant onboarding</p>
            <p>Role-based access for admins and accountants</p>
            <p>Password reset without shared demo credentials</p>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-8 shadow-xl">
          <Link
            href="/"
            title="Return to the app entry route. You will be redirected to login or dashboard based on your session."
            className="text-sm font-medium text-emerald-700 hover:underline"
          >
            VN Accounting
          </Link>
          <h2 className="mt-6 text-3xl font-semibold">{title}</h2>
          <p className="mt-2 text-sm text-slate-500">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </section>
      </div>
    </main>
  );
}
