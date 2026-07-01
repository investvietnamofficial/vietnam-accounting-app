# TODO.md

## High Priority

- [x] Wire real SMTP email delivery for password reset (tokens are generated but no email is sent). → `backend/app/services/email/`
- [x] Implement Google Cloud Vision as production OCR provider with clean provider architecture (google/paddle/mock). → `backend/app/services/ocr/providers.py`, `google_vision.py`, `vision_service.py`
- [x] Persist full OCR metadata (provider, duration_ms, page_count, language, engine_version, warnings, per-page breakdown). → Migration `007_add_ocr_metadata`, `tasks.py`, `documents.py`
- [ ] Add invoice list filters in backend and web: date range, VAT rate, seller/buyer, and GDT verification status.
- [ ] Persist tax-report adjustment inputs as a filing-draft model instead of passing them as transient query parameters.
- [ ] Expose the existing backend failed-document retry route in the web UI.
- [ ] Implement PDF VAT export (`reports.py` currently returns HTTP 501).
- [x] Define a production deployment target and replace dev-only startup commands (`uvicorn --reload`, `npm run dev`). → `docker-compose.prod.yml`, `backend/Dockerfile`, `web/Dockerfile`

## Medium Priority

- [ ] Add gold-fixture regression coverage for VNPT, VIETTEL, and MISA invoice samples.
- [ ] Add public holiday-aware deadline handling for VAT/CIT filing dates (currently only weekends).
- [ ] Expand role enforcement beyond baseline authenticated access on non-auth routes.
- [ ] Add document security scanning and clearer file-validation telemetry.
- [ ] Add invoice detail view with GDT verification notes instead of the current table-only workflow.
- [x] Replace broad `dict` payload handling in `companies.py` with typed Pydantic schemas. → `CompanySettingsUpdate` with `extra="forbid"`
- [ ] Build all web pages on typed API responses instead of `any`-heavy rendering paths.

## Technical Debt

- [x] Remove or explicitly quarantine `seed_demo_data()` and any remaining demo-mode assumptions. → removed from `backend/app/main.py`
- [ ] Resolve legacy/stale docs drift between `README.md`, `docs/CODEX_HANDOFF.md`, and the new root docs.
- [ ] Run Google Cloud Vision real-credentials smoke test (1 PDF invoice, 1 scanned image, 1 photographed image) to measure actual OCR quality and timing. See `docs/GOOGLE_VISION_SETUP.md` for credentials setup.
- [ ] Normalize timezone handling where `datetime.utcnow()` is still used directly.
- [x] Review local-storage fallback assumptions in `r2_service.py` for clearer dev/prod separation. → signed URL support, security comments
- [ ] Complete mobile router and scanner-only status or formally mark the mobile client as experimental.

---

## Future Roadmap

The following features are intentionally deferred. They are valid, valuable products — but they are not part of the Upload → OCR → Extract → Verify → Report → Export core. Do not build these until the core flow is production-hardened.

### Core Flow Extensions
- [ ] Filing submission workflows (GDT portal e-filing integration, draft sign-off, submission history)
- [ ] PDF VAT export that mirrors the official 01/GTGT workbook layout
- [ ] Automated anomaly checks for invalid MSTs, VAT mismatches, and extraction confidence drops

### Accounting Bookkeeping (experimental — models exist, no UI/API)
- [ ] Journal entry authoring UI (POST/PATCH/DELETE journal entries, post/reverse workflow)
- [ ] Chart of accounts UI (seed standard COA, company-level customization)
- [ ] CIT provisional endpoint requires posted journal entries to be meaningful — wire JE flow first

### Tenant Operations
- [ ] Multi-period tax calendar views and filing reminders per tenant
- [ ] Per-tenant filing history and audit trail

### Mobile
- [ ] Mobile dashboard and invoice list views (router has only `/scanner`; `/dashboard`, `/invoices`, `/login` are stub TODOs)
- [ ] Offline upload queue with sync-on-reconnect

### Full-Stack Accounting (out of scope entirely)
- [ ] Payroll module
- [ ] Inventory management
- [ ] Full ERP workflows
