# TODO.md

## High Priority

- [ ] Replace password-reset token display with real SMTP-backed delivery and audit the full reset flow end to end.
- [ ] Finish company settings API and UI for accounting standard, VAT filing period, and tenant profile management.
- [ ] Add invoice list filters in backend and web for date range, VAT rate, seller/buyer, and verification status.
- [ ] Expose failed-document and retry workflow in the web UI using the existing backend retry route.
- [ ] Harden report workflows with persisted adjustment inputs or a filing-draft model instead of transient query params.
- [ ] Add production-grade deployment path for backend, worker, web, env management, and non-dev startup commands.

## Medium Priority

- [ ] Add gold-fixture regression coverage for VNPT, VIETTEL, and MISA invoice samples.
- [ ] Add public-holiday-aware deadline handling for VAT/CIT filing dates.
- [ ] Expand role enforcement beyond baseline authenticated access on non-auth routes.
- [ ] Add document security scanning and clearer file-validation telemetry.
- [ ] Add operator detail view for invoice/GDT verification notes instead of the current table-only workflow.
- [ ] Build dashboard and invoices pages on typed API responses instead of `any`-heavy rendering paths.

## Technical Debt

- [ ] Remove or explicitly quarantine `seed_demo_data()` and any remaining demo-mode assumptions.
- [ ] Resolve legacy/stale docs drift between `README.md`, `docs/CODEX_HANDOFF.md`, and the new root docs.
- [ ] Replace broad `dict` payload handling in `companies.py` with typed schemas and validation.
- [ ] Normalize timezone handling where `datetime.utcnow()` is still used directly.
- [ ] Review local-storage fallback assumptions in `r2_service.py` for clearer dev/prod separation.
- [ ] Finish mobile router and offline-upload TODOs or mark the mobile client as experimental in-product.

## Future Ideas

- [ ] Persist filing drafts, attachments, reviewer sign-off, and filing history per period.
- [ ] Add PDF export that mirrors the 01/GTGT workbook layout.
- [ ] Add accounting journal-entry authoring UI on top of the existing models.
- [ ] Add automated anomaly checks for invalid MSTs, VAT mismatches, and extraction confidence drops.
- [ ] Add multi-period tax calendar views and reminders per tenant.
