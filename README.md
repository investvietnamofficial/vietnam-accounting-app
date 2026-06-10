# VN Accounting Compliance Platform

A full-stack accounting compliance system for Vietnam, consisting of:
- **Backend** — FastAPI (Python) with OCR, AI extraction, Vietnam tax rules
- **Web App** — Next.js 14 dashboard for accounting and tax reporting
- **Mobile App** — Flutter scanner app for capturing invoices

## Architecture

```
mobile (Flutter)  →  backend (FastAPI + Celery)  →  web (Next.js)
      |                      |                            |
  camera scan          OCR + AI extract            tax dashboard
  offline queue        VN compliance check         VAT/CIT reports
  upload image         PostgreSQL + Redis           e-invoice sync
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Flutter 3.x
- Docker & Docker Compose
- PostgreSQL 15
- Redis 7

### 1. Backend
```bash
cd backend
cp .env.example .env          # fill in API keys
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The API no longer creates tables on startup. A database must be reachable and
migrations must succeed before `uvicorn` or the worker will boot cleanly.

### 2. Web App
```bash
cd web
cp .env.local.example .env.local
npm install
npm run dev
```

### 3. Mobile App
```bash
cd mobile
flutter pub get
flutter run
```

### 4. Full stack with Docker
```bash
docker compose up --build
```

The `backend` and `worker` services run `alembic -c alembic.ini upgrade head`
before starting their main process, so the compose path is migration-first by
default.

### Migration smoke check

Use the repo helper to validate the initial upgrade/downgrade path against the
compose PostgreSQL service:

```bash
bash scripts/smoke-migrations.sh
```

This script starts `postgres`, points Alembic at `localhost:55432`, runs
`upgrade head`, `downgrade base`, and `upgrade head` again, then stops the
database container.

## Environment Variables

See `backend/.env.example` and `web/.env.local.example` for all required keys.

Key services needed:
- `GOOGLE_VISION_API_KEY` — OCR for Vietnamese text
- `ANTHROPIC_API_KEY` — AI field extraction
- `DATABASE_URL` — PostgreSQL (Supabase recommended)
- `REDIS_URL` — Job queue
- `R2_*` — Cloudflare R2 for document storage
- `GDT_API_*` — Vietnam General Department of Taxation e-invoice API

## Project Structure

```
vn-accounting/
├── backend/               FastAPI backend
│   ├── app/
│   │   ├── api/routes/    REST endpoints
│   │   ├── core/          Config, security, database
│   │   ├── models/        SQLAlchemy ORM models
│   │   ├── schemas/       Pydantic request/response schemas
│   │   ├── services/      Business logic
│   │   │   ├── ocr/       Google Vision + preprocessing
│   │   │   ├── extraction/ Claude AI field extraction
│   │   │   ├── tax/       VN tax rules engine
│   │   │   └── einvoice/  GDT e-invoice integration
│   │   └── workers/       Celery async jobs
│   ├── alembic/           DB migrations
│   └── tests/
├── web/                   Next.js 14 web app
│   └── src/
│       ├── app/           App Router pages
│       ├── components/    Reusable UI components
│       ├── hooks/         React Query hooks
│       ├── lib/           API client, utils
│       └── types/         TypeScript types
├── mobile/                Flutter scanner app
│   └── lib/
│       ├── features/      Scanner, dashboard features
│       └── core/          Services, models
├── docs/                  API docs, compliance notes
└── docker-compose.yml
```

## Vietnam Compliance Notes

- **VAT rates**: 0%, 5%, 8%, 10% — engine handles all tiers
- **Chart of accounts**: Follows Circular 200/2014/TT-BTC (large enterprises) and Circular 133 (SMEs)
- **VAT declarations**: Mẫu 01/GTGT (monthly/quarterly)
- **e-Invoice**: Nghị định 123/2020/NĐ-CP — GDT API integration required
- **CIT**: Quarterly provisional + annual finalization
- **MST validation**: 10-digit or 13-digit tax codes

## Codex Handoff Notes

Each service has a `TODO` comment block marking what needs full implementation.
The scaffolding, types, interfaces, and integration points are all wired up.
Focus areas for Codex:
1. `backend/app/services/extraction/` — Claude prompt engineering for field extraction
2. `backend/app/services/tax/` — Vietnam tax rule engine logic
3. `web/src/app/reports/` — VAT/CIT report generation UI
4. `mobile/lib/features/scanner/` — Camera pipeline and upload flow

## Schema notes

- Alembic is the source of truth for schema changes under `backend/alembic/`.
- The initial revision now uses explicit Alembic operations instead of
  metadata-driven `create_all/drop_all`.
- Any environment that previously depended on implicit table creation in
  `backend/app/main.py` must run migrations first.
