# AGENTS.md

This file is the single source of truth for AI agents working in `vn-accounting`. If README, old handoff docs, or code comments conflict with this file, trust this file and then verify against code.

## Product

VN Accounting is a **lean VAT-reporting product** — nothing else is in scope until the core flow is production-hardened.

**The only product:**
> Upload → OCR → Extract → Verify → Report → Export

**Target user:** Paying customers who need VAT-ready tax reports from uploaded accounting documents.

What this means in practice:
- FastAPI backend handles document upload, OCR+extraction pipeline, GDT e-invoice verification, and VAT/CIT report generation with XLSX export.
- Next.js 14 web app provides the authenticated operator workflow: upload, review invoices, run reports, export.
- Flutter mobile app provides invoice capture and upload (scanner-first; other mobile flows are ROADMAP).
- All monetary values are stored as integer VND.

What this product does NOT include (ROADMAP / deferred):
- Full accounting system (journal entries, chart of accounts UI, general ledger)
- Filing submission workflows
- Payroll, inventory, or multi-period bookkeeping
- Role enforcement beyond baseline auth
- PDF export (stub only)

## Architecture

- `backend/app/main.py`: FastAPI entrypoint with lifespan boot and route registration.
- `backend/app/api/routes/`: routers for `auth`, `companies`, `documents`, `invoices`, `reports`.
- `backend/app/models/__init__.py`: SQLAlchemy models. Core models for the product are `Document` and `Invoice`. `JournalEntry` and `ChartOfAccount` exist but are not yet wired into the core flow (see ROADMAP).
- `backend/app/workers/tasks.py`: document-processing pipeline; Celery path or inline local fallback.
- `backend/app/services/ocr/`: OCR extraction and preprocessing.
- `backend/app/services/extraction/`: structured invoice extraction from OCR text.
- `backend/app/services/einvoice/`: GDT verification client.
- `backend/app/services/tax/`: VAT/CIT helpers and filing logic.
- `backend/app/services/storage/r2_service.py`: R2 or local filesystem storage.
- `web/src/app/`: authenticated dashboard, invoices, reports, auth flows.
- `web/src/lib/api.ts`: axios client and web/backend contract.
- `mobile/lib/`: scanner-first Flutter client; other mobile flows are deferred.

Data shape assumptions:
- Monetary values are stored as integer VND.
- Alembic migrations are the schema source of truth.
- Web types in `web/src/types/index.ts` should track backend response shape closely.

## Tech Stack

- Backend: Python 3.11, FastAPI, SQLAlchemy 2, Alembic, asyncpg, Celery, Redis, structlog.
- OCR/document: PaddleOCR, pdf2image, Pillow, optional Google Vision fallback.
- Extraction: Anthropic SDK integration plus regex fallback.
- Storage: Cloudflare R2 via boto3, with local storage fallback.
- Web: Next.js 14 App Router, React 18, TypeScript, React Query, axios, Tailwind, lucide-react.
- Mobile: Flutter, Riverpod, GoRouter.
- Local orchestration: Docker Compose with Postgres 15 + Redis 7.

## Important Directories

- `backend/app/api/routes`: API behavior and business entrypoints.
- `backend/app/models`: database model definitions.
- `backend/alembic/versions`: migration history.
- `backend/tests`: backend verification suite.
- `backend/scripts`: helper scripts, including GDT verification CLI.
- `web/src/app`: route-level UI.
- `web/src/components`: shared UI wrappers/providers.
- `web/src/hooks`: React Query hooks.
- `web/src/lib`: API client and utility glue.
- `mobile/lib/features`: scanner/mobile feature code.
- `docs`: legacy notes only; do not assume current.
- `scripts`: repo-level helpers like migration smoke tests.

## Run

Preferred repo root: `/Users/gilbertneo/Desktop/My Apps/Vietnam Accounting App/vn-accounting`

Backend local:
```bash
cd backend
cp .env.example .env
../.venv311/bin/pip install -r requirements.txt
PYTHONPATH=backend ../.venv311/bin/alembic -c alembic.ini upgrade head
PYTHONPATH=backend ../.venv311/bin/uvicorn app.main:app --reload
```

Web local:
```bash
cd web
cp .env.local.example .env.local
npm install
npm run dev
```

Compose path:
```bash
docker compose up --build
```

Default local ports:
- Postgres: `55432`
- Backend: `8000`
- Web: `3000`

## Test

Focused backend suite that has been used successfully:
```bash
PYTHONPATH=backend ./.venv311/bin/python -m pytest \
  backend/tests/test_tax_engine.py \
  backend/tests/test_reports_logic.py \
  backend/tests/test_auth_security.py \
  backend/tests/test_document_pipeline.py \
  backend/tests/test_einvoice_service.py \
  backend/tests/test_extraction_accuracy.py -q
```

Web typecheck:
```bash
cd web
./node_modules/.bin/tsc --noEmit -p tsconfig.json
```

Migration smoke:
```bash
bash scripts/smoke-migrations.sh
```

## Deploy

Current deploy story is development-oriented only:
- `docker-compose.yml` is the primary working deployment path.
- `backend` and `worker` auto-run Alembic before boot.
- `web` runs `npm run dev`, not a hardened production server.
- There is no production-grade deployment manifest in repo yet.

Do not describe this repo as production-ready.

## Coding Conventions

- Keep backend async where the route/service already uses async patterns.
- Use Alembic for schema changes; do not reintroduce implicit `create_all`.
- Preserve integer VND semantics for monetary values.
- Keep backend/web contract synchronized through `web/src/types/index.ts` and `web/src/lib/api.ts`.
- Prefer small, direct patches over broad rewrites.
- When running backend tests from repo root, set `PYTHONPATH=backend`.
- Treat `docs/CODEX_HANDOFF.md` and README as legacy context, not canonical state.
- New agent-facing session status belongs in `TODO.md` and `HANDOFF.md`.

## Do Not Modify Without Approval

- `backend/alembic/versions/` and schema shape in `backend/app/models/__init__.py`.
- Auth/session/token logic in `backend/app/api/routes/auth.py`, `backend/app/core/security.py`, and `web/src/components/auth-provider.tsx`.
- Filing logic in `backend/app/api/routes/reports.py` and `backend/app/services/tax/vn_tax_engine.py`.
- GDT verification behavior in `backend/app/services/einvoice/`.
- OCR/extraction pipeline in `backend/app/services/ocr/`, `backend/app/services/extraction/`, and `backend/app/workers/tasks.py`.
- Storage behavior in `backend/app/services/storage/r2_service.py`.
- Docker/boot flow in `docker-compose.yml`, `backend/Dockerfile`, and migration startup commands.

## Current Reality Check

**What works:**
- Tenant registration (company + admin user)
- Document upload → OCR → extraction pipeline (upload/OCR/extract/verify end-to-end)
- Invoice records created automatically from extracted data
- GDT e-invoice verification (gracefully degrades if not configured)
- VAT summary with full 01/GTGT declaration field computation
- Invoice list report with purchase/sales annexes
- CIT provisional calculation (requires posted journal entries to be meaningful)
- XLSX export of VAT declaration with annex sheets
- JWT auth with refresh token rotation
- Web TypeScript compile passes

**What is partial or not yet production-ready:**
- Password reset generates tokens but does not send real email.
- Invoice list has no filters (date, VAT rate, seller, verification status).
- Company settings API (`companies.py`) returns raw models, not full typed settings.
- Failed-document retry exists in backend but is not exposed in the web UI.
- PDF VAT export is not implemented (returns HTTP 501).
- Report adjustments are passed as query parameters, not persisted.
- Invoice/GDT verification notes view is table-only.
- CIT provisional depends on `JournalEntry` records — no JE authoring UI exists yet.
- Public holiday-aware filing deadline handling is not implemented (only weekends accounted for).
- Mobile app is scanner-only; dashboard/invoices/login routes are stub TODOs.
- Chart of accounts and journal entry models exist in DB but have no authoring UI or dedicated API.
- Local git history is absent in the current workspace snapshot.

## Session Discipline

- Update `TODO.md` and `HANDOFF.md` before ending every session.
- Keep `AGENTS.md` stable and canonical; only change it when repo truth changes.
- If you make claims about readiness, tests, or deployment, tie them to commands that were actually run.
