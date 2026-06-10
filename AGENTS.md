# AGENTS.md

This file is the single source of truth for AI agents working in `vn-accounting`. If README, old handoff docs, or code comments conflict with this file, trust this file and then verify against code.

## Product

VN Accounting is a tenant-aware Vietnam accounting compliance product with:
- FastAPI backend for auth, document ingestion, OCR/extraction, invoice storage, GDT e-invoice verification, and VAT/CIT reporting.
- Next.js 14 web app for authenticated dashboard, invoice review, and tax-report workflows.
- Flutter mobile scanner app for invoice capture and upload.

Core flow:
1. Register a tenant and admin user.
2. Upload invoice image/PDF.
3. Store file in R2 or local storage fallback.
4. OCR + extraction create/update invoice records.
5. Operators review invoices and generate VAT/CIT reporting outputs.

## Architecture

- `backend/app/main.py`: FastAPI entrypoint with lifespan boot and route registration.
- `backend/app/api/routes/`: routers for `auth`, `companies`, `documents`, `invoices`, `reports`.
- `backend/app/models/__init__.py`: SQLAlchemy models for companies, users, documents, invoices, chart of accounts, journal entries.
- `backend/app/workers/tasks.py`: document-processing pipeline; Celery path or inline local fallback.
- `backend/app/services/ocr/`: OCR extraction and preprocessing.
- `backend/app/services/extraction/`: structured invoice extraction from OCR text.
- `backend/app/services/einvoice/`: GDT verification client.
- `backend/app/services/tax/`: VAT/CIT helpers and filing logic.
- `web/src/app/`: authenticated dashboard, invoices, reports, auth flows.
- `web/src/lib/api.ts`: axios client and web/backend contract.
- `mobile/lib/`: scanner-first Flutter client; still incomplete.

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

- Backend auth, upload, OCR/extraction, invoice persistence, GDT verification, and reporting routes exist.
- Report logic is stronger than the old MVP version but still depends on operator-provided adjustment inputs and accurate posted journal entries.
- Invoice filters and company settings APIs are still partial.
- Mobile app is not production-ready.
- Password reset is token-based but does not send real email.
- Local git history is absent in the current workspace snapshot unless initialized during the current session.

## Session Discipline

- Update `TODO.md` and `HANDOFF.md` before ending every session.
- Keep `AGENTS.md` stable and canonical; only change it when repo truth changes.
- If you make claims about readiness, tests, or deployment, tie them to commands that were actually run.
