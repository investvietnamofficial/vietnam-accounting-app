# Codex Handoff Document

## Current Architecture

- Monorepo at `/Users/gilbertneo/Desktop/My Apps/Vietnam Accounting App/vn-accounting` with `backend/` (FastAPI), `web/` (Next.js 14 App Router), `mobile/` (Flutter), `docs/`, and `scripts/`.
- Backend entrypoint is [backend/app/main.py](/Users/gilbertneo/Desktop/My%20Apps/Vietnam%20Accounting%20App/vn-accounting/backend/app/main.py:1). Active API routers are `auth`, `companies`, `documents`, `invoices`, and `reports`.
- ORM models live in [backend/app/models/__init__.py](/Users/gilbertneo/Desktop/My%20Apps/Vietnam%20Accounting%20App/vn-accounting/backend/app/models/__init__.py:1). `Document` tracks checksum, retry/error metadata, and a `failed` state. `Invoice` stores extracted invoice fields and GDT verification fields.
- Alembic is the schema source of truth. Current revisions are `001_initial_schema.py` and `002_document_pipeline_hardening.py`.
- Auth is JWT-based. Backend supports registration, login, `auth/me`, forgot/reset password, refresh-token flow, and basic role information on the user model. The web app stores JWTs in local storage and protects authenticated pages.
- Document processing flow is implemented as upload -> storage -> async/background processing -> OCR -> extraction -> invoice upsert -> optional GDT verification. It supports checksum-based duplicate detection and retry of failed or rejected documents.
- OCR and extraction are materially beyond the original skeleton. OCR supports preprocessing variants and extraction includes VNPT, VIETTEL, and MISA-aware guidance plus deterministic fallback parsing when confidence is low.
- Web frontend uses `axios` plus React Query. `/dashboard`, `/invoices`, and `/reports` are protected with the auth provider and redirect unauthenticated users to `/auth/login`.

## Deployment Setup

- Primary local run path is Docker Compose via [docker-compose.yml](/Users/gilbertneo/Desktop/My%20Apps/Vietnam%20Accounting%20App/vn-accounting/docker-compose.yml:1).
- Compose services are `postgres` (`15-alpine`), `redis` (`7-alpine`), `backend`, `worker`, and `web`.
- `backend` and `worker` both run `alembic -c alembic.ini upgrade head` before starting their main process.
- Default ports:
  - Postgres: `localhost:55432`
  - Backend: `localhost:8000`
  - Web: `localhost:3000`
- Compose is still development-oriented. `backend` runs `uvicorn --reload`, `web` runs `npm run dev`, and the Docker setup should not be treated as a production runtime recipe.
- Migration smoke helper exists at [scripts/smoke-migrations.sh](/Users/gilbertneo/Desktop/My%20Apps/Vietnam%20Accounting%20App/vn-accounting/scripts/smoke-migrations.sh:1). It boots compose Postgres, creates a temporary DB, then runs upgrade -> downgrade -> upgrade.

## Staging Flow

1. Create `backend/.env` from `backend/.env.example` if you need non-default settings.
2. Start the stack with `docker compose up --build`.
3. Let `backend` and `worker` auto-run Alembic on boot.
4. Verify backend health at `GET /health`.
5. Verify auth first: register a company, log in, and confirm protected web pages load without any demo login shortcut.
6. Exercise the document path: upload an invoice or PDF, poll `GET /api/v1/documents/{id}`, and confirm OCR/extraction/invoice creation.
7. If needed, run `bash scripts/smoke-migrations.sh` to validate migrations against compose Postgres.
8. Focused backend validation currently passes with:
   - `PYTHONPATH=backend ./.venv311/bin/python -m pytest backend/tests/test_auth_security.py backend/tests/test_document_pipeline.py backend/tests/test_einvoice_service.py backend/tests/test_extraction_accuracy.py -q`

## Env Structure

- Core/runtime:
  - `APP_ENV`, `APP_SECRET_KEY`, `APP_DEBUG`, `ALLOWED_ORIGINS`
- Database/cache:
  - `DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`
- Auth:
  - `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`
  - `SEED_DEMO_DATA` defaults to `false`
- OCR:
  - `OCR_ENGINE`, `PADDLEOCR_LANG`, `PADDLEOCR_USE_GPU`, `PADDLEOCR_TIMEOUT_SECONDS`
  - optional Google Vision fallback via `GOOGLE_VISION_API_KEY` or `GOOGLE_APPLICATION_CREDENTIALS`
- AI extraction:
  - `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- Storage:
  - `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`, `LOCAL_STORAGE_DIR`
- Async processing:
  - `USE_CELERY`
- GDT:
  - `GDT_API_BASE_URL`, `GDT_API_USERNAME`, `GDT_API_PASSWORD`, `GDT_TAX_CODE`
- Email:
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- Web:
  - `NEXT_PUBLIC_API_URL`

## Pending Tasks

- Add real password reset delivery via email. Backend can generate reset tokens, but there is no actual mailer flow.
- Expand RBAC beyond the current baseline. User roles exist, but most routes are effectively authenticated-user access rather than deeper admin/accountant/viewer enforcement.
- Add real upload security or malware scanning. The document pipeline is more robust now, but there is still no scanning layer.
- Add operator UI for failed documents and retry flow. Backend exposes retry endpoints; the web app does not expose an operations workflow for it yet.
- Add invoice regression fixtures using real VNPT, VIETTEL, and MISA samples. Current extraction improvements are not benchmarked against a gold scanned-invoice dataset.
- Finish production deployment hardening. Dockerfiles and compose remain dev-oriented.
- Decide whether `SEED_DEMO_DATA` and the `seed_demo_data()` path should remain in the codebase.
- Reports are still partial. VAT summary, invoice list, and CIT provisional endpoints exist, but some code paths still contain explicit MVP/TODO notes and simplified calculations.
- Invoices UI/backend are still partial. Backend listing exists, but server-side invoice filters described in earlier planning are not implemented yet.

## Important Warnings

- The old handoff document in this repo was stale and described mostly TODO work. This document replaces it with the current verified state as of June 6, 2026.
- Focused backend tests passed locally, but they require `PYTHONPATH=backend` when run from the repo root.
- Docker-backed migration smoke depends on the local Docker daemon actually running.
- Compose is a development stack, not a production deployment recipe.
- Password reset is token-generation only. In non-production it may return the reset token directly; production still needs real email delivery.
- OCR and extraction are improved, but they are still heuristic plus model-based and are not yet backed by a scanned-invoice gold dataset.
- Local storage fallback still exists when R2 is not configured. That is useful for development but should not be treated as the final production storage strategy.
- GDT verification integration exists, but live correctness still depends on real credentials and the exact reachable GDT auth/query endpoints.
- The mobile app is present, but it should not be treated as production-ready.
