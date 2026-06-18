# HANDOFF.md

## Current Repository Status

- Active codebase lives in `vn-accounting/` with backend, web, mobile, docs, and scripts.
- **Product focus is lean**: Upload → OCR → Extract → Verify → Report → Export only. No full accounting system, payroll, or inventory.
- Backend supports: tenant registration, document upload/OCR/extraction, invoice persistence, GDT e-invoice verification, VAT/CIT reporting with XLSX export.
- Web app has: authenticated dashboard, upload flow, invoices table, reports with VAT summary and annexes, XLSX download.
- Mobile app is scanner-only: `/scanner` route works; `/dashboard`, `/invoices`, `/login` are stub TODOs in the router.
- Docker Compose is the only working full-stack run path; it is still dev-oriented.
- Verified June 10, 2026: focused backend suite passed and web TypeScript compile passed.

## Recent Findings

- **Phase 1 product audit completed.** All files have been classified as KEEP / ROADMAP / MOBILE-ONLY / EXPERIMENTAL / LEGACY. AGENTS.md, TODO.md, and this file have been updated to reflect the lean scope.
- Reporting logic computes full 01/GTGT declaration fields, not just MVP aggregates. Still depends on operator-supplied adjustment inputs (not yet persisted).
- `companies.py` returns raw SQLAlchemy models in some routes instead of typed response schemas.
- Password reset generates JWT tokens but does not send real email.
- CIT provisional calculation requires posted journal entries to be meaningful — no JE authoring UI exists.
- `JournalEntry` and `ChartOfAccount` models exist in the DB schema but have no authoring routes or UI.
- Mobile router only exposes `/scanner`; other routes are TODO stubs.
- Verified commands:
  - `PYTHONPATH=backend ./.venv311/bin/python -m pytest backend/tests/test_tax_engine.py backend/tests/test_reports_logic.py backend/tests/test_auth_security.py backend/tests/test_document_pipeline.py backend/tests/test_einvoice_service.py backend/tests/test_extraction_accuracy.py -q`
  - `cd web && ./node_modules/.bin/tsc --noEmit -p tsconfig.json`

## Known Issues

- No production deployment recipe; current compose stack runs `uvicorn --reload` and `npm run dev`.
- Invoice list has no filters (date, VAT rate, seller, GDT status).
- Report adjustments are query params, not persisted (filing draft model needed).
- PDF VAT export returns HTTP 501.
- Failed-document retry exists in backend but not exposed in web UI.
- Mobile dashboard/invoices/login routes are stub TODOs.
- Filing deadlines only account for weekends, not Vietnam public holidays.
- `companies.py` uses broad `dict` payloads instead of typed Pydantic schemas.
- `seed_demo_data()` may still exist somewhere; needs quarantine.
- Local git history is absent in the current workspace snapshot.

## Pending Tasks (lean scope)

1. Wire real SMTP email delivery for password reset.
2. Add invoice list filters (backend + web): date range, VAT rate, seller/buyer, GDT verification status.
3. Persist tax-report adjustment inputs as a filing-draft model.
4. Expose failed-document retry in the web UI.
5. Implement PDF VAT export (currently returns HTTP 501).
6. Define production deployment target.

## Recommended Next Actions

1. Complete invoice list filters first — operators cannot work with large invoice sets without them.
2. Wire real email delivery for password reset before any real-user testing.
3. Add filing-draft persistence model before any real filing usage (adjustments currently lost on refresh).
4. Once core upload→report flow is validated by real users, address PDF export and production deploy hardening.
5. All other items (journal entries, chart of accounts UI, payroll, inventory, multi-period calendar) are ROADMAP — do not start until the core flow has paying users.

## MiniMax Handoff Prompt

Use `AGENTS.md` as the only canonical repo brief. The product scope is strictly Upload → OCR → Extract → Verify → Report → Export. Audit current code before making assumptions. Work inside `vn-accounting/`. Prefer the Docker Compose path for full-stack validation, and use `PYTHONPATH=backend` for backend tests from repo root. Treat these areas as sensitive and do not modify them without explicit approval: Alembic/schema, auth/security, tax filing logic, GDT integration, OCR/extraction pipeline, storage behavior, and boot/deploy flow. Update `TODO.md` and `HANDOFF.md` before ending the session.
