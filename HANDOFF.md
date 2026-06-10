# HANDOFF.md

## Current Repository Status

- Active codebase lives in `vn-accounting/` with backend, web, mobile, docs, and scripts.
- Backend supports auth, document upload, OCR/extraction, invoice persistence, GDT verification, and filing-oriented VAT/CIT reporting.
- Web app has authenticated dashboard, invoices, and reports flows and a broad native-tooltip pass across current screens.
- Mobile app exists but is still scanner-first and incomplete.
- Docker Compose is the only working full-stack run path in-repo, and it is still dev-oriented.
- Verified on June 10, 2026: focused backend suite passed and the web TypeScript compile passed.

## Recent Findings

- Reporting logic is no longer the earlier VAT/CIT MVP shortcut path; it now computes declaration fields and annex exports, but still depends on user-supplied filing adjustments and posted journal-entry coverage.
- `companies.py` and `invoices.py` still contain partial TODO-grade API behavior.
- Password reset still generates tokens without real email delivery.
- README and `docs/CODEX_HANDOFF.md` are not reliable as canonical agent docs.
- The workspace snapshot did not include a git repository when this session started.
- Verified commands:
  - `PYTHONPATH=backend ./.venv311/bin/python -m pytest backend/tests/test_tax_engine.py backend/tests/test_reports_logic.py backend/tests/test_auth_security.py backend/tests/test_document_pipeline.py backend/tests/test_einvoice_service.py backend/tests/test_extraction_accuracy.py -q`
  - `./node_modules/.bin/tsc --noEmit -p tsconfig.json`

## Known Issues

- No production deployment recipe; current compose stack runs `uvicorn --reload` and `npm run dev`.
- Invoice list lacks filtering/search beyond basic pagination.
- Company settings endpoints are under-typed and only partially implemented.
- Failed-document retry exists in backend but not in the web UI.
- Mobile router still only exposes the scanner route.
- PDF VAT export is not implemented.
- Filing deadlines only account for weekends, not Vietnam public holidays.

## Pending Tasks

- Implement SMTP-backed password reset delivery.
- Complete company settings API/UI.
- Add invoice filters and richer review surfaces.
- Persist tax-report adjustments or filing drafts instead of relying on query params.
- Add production deployment hardening.
- Expand fixture-based OCR/extraction regression coverage.

## Recommended Next Actions

1. Wire real email delivery for password reset and verify auth flows end to end.
2. Finish company settings and invoice filtering so operators can manage tenants and large invoice sets.
3. Add persisted filing-draft storage for VAT/CIT adjustments before any real filing usage.
4. Expose failed-document retry and richer invoice review details in the web app.
5. Define a real deployment target and replace dev-only startup commands.

## MiniMax Handoff Prompt

Use `AGENTS.md` as the only canonical repo brief. Audit current code before making assumptions. Work inside `vn-accounting/`. Prefer the Docker Compose path for full-stack validation, and use `PYTHONPATH=backend` for backend tests from repo root. Treat these areas as sensitive and do not modify them without explicit approval: Alembic/schema, auth/security, tax filing logic, GDT integration, OCR/extraction pipeline, storage behavior, and boot/deploy flow. Update `TODO.md` and `HANDOFF.md` before ending the session.
