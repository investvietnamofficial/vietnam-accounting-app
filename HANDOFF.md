# VN Accounting — Handoff Document
**Generated:** 2026-07-01 | **Author:** Mavis (MiniMax Agent) | **Repo:** `github.com/gilbertneo/vn-accounting`

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Next.js 14 Web App                       │
│         http://localhost:3001  (production: TBD)            │
└─────────────────────┬───────────────────────────────────────┘
                      │ REST / JWT
┌─────────────────────▼───────────────────────────────────────┐
│                   FastAPI Backend                            │
│                  http://localhost:8000                        │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Auth Route  │  │  Docs Route  │  │ Reports Route  │  │
│  │   /api/v1/   │  │   /api/v1/   │  │   /api/v1/     │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Document Processing Pipeline              │  │
│  │                                                       │  │
│  │  Upload → OCR → Extract → Update DB → Invoice gen  │  │
│  │                                                       │  │
│  │  OCR Layer:                                           │  │
│  │    PaddleOCR (default) → google_vision.py (fallback) │  │
│  │                                                       │  │
│  │  Extraction Layer:                                    │  │
│  │    DeepSeek (production, api.deepseek.com)           │  │
│  │    → Claude/Anthropic (fallback)                     │  │
│  │    → RegexFallbackExtractor (offline/dev mode)       │  │
│  │                                                       │  │
│  │  GDT e-Invoice Verification:                         │  │
│  │    app/services/einvoice/gdt_service.py              │  │
│  │    (gracefully degrades if not configured)           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
          ┌───────────┼───────────┐
          │           │           │
    ┌─────▼───┐  ┌────▼────┐  ┌───▼────┐
    │Postgres  │  │  Redis  │  │Local FS│
    │   5432   │  │  6379   │  │storage │
    └─────────┘  └─────────┘  └────────┘
```

**Repo structure:**
```
vn-accounting/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI route handlers
│   │   ├── core/              # config, database, security
│   │   ├── models/            # SQLAlchemy models
│   │   ├── services/
│   │   │   ├── ocr/           # PaddleOCR + Google Vision
│   │   │   ├── extraction/    # DeepSeek + Claude + regex
│   │   │   ├── einvoice/      # GDT verification
│   │   │   ├── storage/       # R2 + local fallback
│   │   │   └── tax/           # VAT/CIT engine
│   │   └── workers/           # Celery tasks
│   ├── alembic/versions/      # Migration history
│   └── tests/                 # pytest suite
├── web/                       # Next.js 14 app
├── docker-compose.yml
└── docs/
```

---

## 2. OCR Flow

### 2.1 Pipeline

```
POST /api/v1/documents/upload
    ↓
R2Service.upload()          # saves file; local fallback if R2 not configured
    ↓
checksum = sha256(content)
_find_existing_document()   # dedup by checksum within company
    ↓
Document created (status=PENDING)
    ↓
_dispatch_processing()      # background task
    ↓
process_document_now()      # runs inline (local) or Celery (production)
    ↓
┌─────────────────────────────────────────────────────────┐
│  1. PREPROCESS                                          │
│     pdf2image + Pillow → list of (page_bytes, page_num)│
│                                                          │
│  2. OCR (selected by settings.ocr_provider)             │
│     default: PaddleOCR                                   │
│     fallback: GoogleVisionOCR                            │
│                                                          │
│  3. EXTRACTION (selected by settings.llm_provider)      │
│     default: DeepSeek via _call_deepseek()              │
│     fallback: Anthropic Claude via AsyncAnthropic SDK    │
│     offline: RegexFallbackExtractor                      │
│                                                          │
│  4. INVOICE GENERATION                                  │
│     Invoice record created from extracted_data            │
│                                                          │
│  5. GDT VERIFICATION (if configured)                   │
│     gdt_service.verify() → update invoice record         │
└─────────────────────────────────────────────────────────┘
    ↓
Document.status = 'extracted' (or 'failed')
```

### 2.2 OCR Providers

**PaddleOCR** (default, no API key needed):
- Runs locally via `paddleocr.PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False)`
- `backend/app/services/ocr/paddle_ocr.py`
- Falls back to Google Vision if PaddleOCR raises an `Exception`

**Google Vision** (fallback, requires `GOOGLE_APPLICATION_CREDENTIALS_JSON`):
- `backend/app/services/ocr/google_vision.py`
- Uses `google.cloud.vision.ImageAnnotatorClient`
- Service account JSON pasted as env var string (not file path)
- Per-page timeout: `max(ocr_timeout_seconds / page_count, 5)` seconds
- Known fix (this audit cycle): `s.symbol.text` → `s.text` (line 383) — symbol objects have `.text` directly, not nested under `.symbol`

### 2.3 Extraction Providers

**DeepSeek** (production, `llm_provider=deepseek`):
- `api.deepseek.com/chat/completions`
- Model: `deepseek-chat` (configurable via `DEEPSEEK_MODEL`)
- Uses standard `chat/completions` API via `urllib.request`
- No SDK dependency

**Anthropic** (fallback, `llm_provider=anthropic`):
- Requires `ANTHROPIC_API_KEY`
- Uses `anthropic.AsyncAnthropic` SDK
- Model: `claude-sonnet-4-20250514`

**Regex fallback** (`llm_provider` unset or placeholder):
- `RegexFallbackExtractor` class in `claude_extractor.py`
- No API calls; pure regex over OCR text
- Used in offline/dev mode

All three paths share the same `EXTRACTION_SYSTEM_PROMPT` defining the JSON output schema.

---

## 3. LLM Flow

### 3.1 Selection Logic

```python
# backend/app/services/extraction/claude_extractor.py  ExtractionService.__init__
self.provider = settings.llm_provider.lower()  # from env LLM_PROVIDER

if self.provider == "deepseek" and settings.deepseek_api_key not in (None, ""):
    → _call_deepseek()
elif self.provider == "anthropic" and settings.anthropic_api_key valid:
    → _call_anthropic()
else:
    → RegexFallbackExtractor.extract()  # offline fallback
```

### 3.2 Prompt

`EXTRACTION_SYSTEM_PROMPT` instructs the LLM to return a JSON object with:
- `invoice_series`, `invoice_number`, `invoice_date`, `invoice_type`
- `seller_name`, `seller_address`, `seller_tax_code`
- `buyer_name`, `buyer_address`, `buyer_tax_code`
- `subtotal_amount`, `vat_rate`, `vat_amount`, `total_amount`
- `line_items` (array of `{name, quantity, unit_price, amount}`)
- `confidence` (0.0–1.0)

Raw JSON is parsed with `json.loads()` and validated. Low confidence (< 0.78) is flagged in the response.

### 3.3 Configuration

```bash
# In backend/.env
LLM_PROVIDER=deepseek              # deepseek | anthropic | (empty=regex-only)
DEEPSEEK_API_KEY=sk-...            # Required for production
DEEPSEEK_MODEL=deepseek-chat       # Default
ANTHROPIC_API_KEY=sk-ant-...       # Fallback only
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

---

## 4. Database Schema

### 4.1 Core Tables

**`companies`**
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | VARCHAR(255) | |
| tax_code | VARCHAR(50) | |
| address | TEXT | |
| created_at | TIMESTAMPTZ | |

**`users`**
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| email | VARCHAR(255) | UNIQUE |
| hashed_password | VARCHAR(255) | |
| full_name | VARCHAR(255) | |
| role | user_role | admin / operator / viewer |
| is_active | BOOLEAN | |
| company_id | UUID | FK → companies.id |

**`documents`** — primary artifact table
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| company_id | UUID | FK → companies.id |
| uploaded_by_id | UUID | FK → users.id |
| file_name | VARCHAR(255) | |
| file_url | TEXT | local:// or r2:// URL |
| file_size_bytes | BIGINT | |
| mime_type | VARCHAR(100) | |
| file_checksum | VARCHAR(64) | SHA-256; used for dedup |
| doc_type | documenttype | invoice / receipt / other |
| status | documentstatus | pending/processing/extracted/failed/rejected |
| duplicate_of_document_id | UUID | Self-ref FK if deduped |
| ocr_raw_text | TEXT | Raw OCR output |
| ocr_confidence | NUMERIC(5,4) | 0.0–1.0 |
| ocr_provider | VARCHAR(50) | google / paddle |
| ocr_engine_version | VARCHAR(50) | e.g. "google-cloud-vision" |
| ocr_duration_ms | INTEGER | |
| ocr_page_count | INTEGER | |
| ocr_language | VARCHAR(50) | e.g. "vi+en" |
| ocr_warnings | TEXT | JSON array as string |
| ocr_pages | JSONB | Per-page OCR results |
| extracted_data | JSONB | Structured extraction output |
| extraction_confidence | NUMERIC(5,4) | |
| celery_job_id | VARCHAR(255) | |
| processing_attempts | INTEGER | |
| processing_started_at | TIMESTAMPTZ | |
| processed_at | TIMESTAMPTZ | |
| processing_error | TEXT | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**`invoices`** — auto-generated from `documents.extracted_data`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| company_id | UUID | FK → companies.id |
| document_id | UUID | FK → documents.id (UNIQUE) |
| invoice_series | VARCHAR(50) | |
| invoice_number | VARCHAR(50) | |
| invoice_date | DATE | |
| doc_type | documenttype | |
| seller_name | VARCHAR(255) | |
| seller_address | TEXT | |
| seller_tax_code | VARCHAR(50) | |
| buyer_name | VARCHAR(255) | |
| buyer_address | TEXT | |
| buyer_tax_code | VARCHAR(50) | |
| subtotal_amount | BIGINT | VND (integer) |
| vat_rate | NUMERIC(5,2) | e.g. 0.00, 0.05, 0.10 |
| vat_amount | BIGINT | VND (integer) |
| total_amount | BIGINT | VND (integer) |
| line_items | JSONB | |
| einvoice_status | einvoicestatus | pending/verified/rejected/not_registered |
| einvoice_verified_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**`journal_entries`** — exists; not yet wired to UI
**`chart_of_accounts`** — exists; not yet wired to UI

### 4.2 Enum Types

```sql
CREATE TYPE documentstatus AS ENUM ('pending', 'processing', 'extracted', 'failed', 'rejected');
CREATE TYPE documenttype AS ENUM ('invoice', 'receipt', 'contract', 'other');
CREATE TYPE user_role AS ENUM ('admin', 'operator', 'viewer');
CREATE TYPE einvoicestatus AS ENUM ('pending', 'verified', 'rejected', 'not_registered');
```

---

## 5. Migrations Applied

All migrations live in `backend/alembic/versions/`. Schema is managed by Alembic only — do NOT use `Base.metadata.create_all()`.

Latest migration confirmed applied: **verify via `alembic current`**.

```bash
# Check migration status
cd backend
PYTHONPATH=backend ../.venv311/bin/alembic -c alembic.ini current

# Apply pending migrations
PYTHONPATH=backend ../.venv311/bin/alembic -c alembic.ini upgrade head

# Create new migration
PYTHONPATH=backend ../.venv311/bin/alembic -c alembic.ini revision --autogenerate -m "description"
```

Note: `alembic/env.py` was patched to use `VARCHAR(64)` instead of `String(64)` for the `version_table_coltype` to fix a PostgreSQL compatibility issue.

---

## 6. Environment Variables

### Backend (`backend/.env`)

```bash
# === APP ===
APP_ENV=development                  # development | production
APP_DEBUG=true                       # enable debug features
SECRET_KEY=<random-32+ chars>        # django-style secret key

# === DATABASE ===
DATABASE_URL=postgresql+asyncpg://vn_accounting:TestPass123!@localhost:5432/vn_accounting
DATABASE_URL_SYNC=postgresql+psycopg2://vn_accounting:TestPass123!@localhost:5432/vn_accounting?sslmode=disable

# === JWT AUTH ===
JWT_SECRET_KEY=<strong-random-key>   # 32+ chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# === STORAGE ===
# Local fallback (default — no R2 needed for dev)
LOCAL_STORAGE_DIR=./storage

# R2 (optional — for production)
# R2_ACCOUNT_ID=...
# R2_ACCESS_KEY_ID=...
# R2_SECRET_ACCESS_KEY=...
# R2_PUBLIC_URL=https://pub-xxx.r2.dev
# R2_BUCKET_NAME=vn-accounting-docs

# === OCR ===
OCR_PROVIDER=google                  # google | paddle (default=paddle)
OCR_TIMEOUT_SECONDS=60
# Google Vision service account JSON (paste entire JSON as string)
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account",...}

# === LLM EXTRACTION ===
LLM_PROVIDER=deepseek               # deepseek | anthropic | (empty=regex-only)
DEEPSEEK_API_KEY=sk-...             # Required for production
DEEPSEEK_MODEL=deepseek-chat
ANTHROPIC_API_KEY=sk-ant-...        # Fallback only
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# === GDT E-INVOICE (optional) ===
# GDT_API_URL=https://...
# GDT_USERNAME=...
# GDT_PASSWORD=...

# === CORS ===
ALLOWED_ORIGINS=["http://localhost:3001","http://localhost:8000"]
```

### Web (`web/.env.local`)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_ENV=development
```

---

## 7. Google Vision Setup

### Prerequisites

1. Create a Google Cloud project at https://console.cloud.google.com
2. Enable the **Cloud Vision API**
3. Create a **Service Account** with the Vision API User role
4. Download the JSON key file
5. Paste the entire JSON content as the value of `GOOGLE_APPLICATION_CREDENTIALS_JSON` in `backend/.env`

```bash
# Example: paste full JSON as single-line string
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type":"service_account","project_id":"my-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...","client_email":"...@....iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token",...}
```

The `google_vision.py` service reads this JSON from the env var and creates credentials without writing to disk.

### Usage

```bash
OCR_PROVIDER=google
```

If `OCR_PROVIDER` is unset or set to `paddle`, Google Vision is only used as a fallback when PaddleOCR fails.

---

## 8. DeepSeek Setup

```bash
# 1. Get API key from https://platform.deepseek.com
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 2. Set provider
LLM_PROVIDER=deepseek

# 3. Optional: change model
DEEPSEEK_MODEL=deepseek-chat  # default
```

No SDK installation required — uses `urllib.request` directly.

---

## 9. Local Startup Instructions

### Prerequisites
- Python 3.11
- Node.js 20+
- PostgreSQL 15 running on port 5432
- Redis 7 running on port 6379 (optional for local dev; Celery uses eager mode)

### Steps

```bash
# 1. Clone
git clone https://github.com/gilbertneo/vn-accounting
cd vn-accounting

# 2. Backend venv
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install -r backend/requirements.txt

# 3. Database
# Ensure Postgres is running and a DB 'vn_accounting' exists
# Create user if needed:
#   CREATE USER vn_accounting WITH PASSWORD 'TestPass123!';
#   CREATE DATABASE vn_accounting OWNER vn_accounting;
#   GRANT ALL ON SCHEMA public TO vn_accounting;

# 4. Apply migrations
cd backend
PYTHONPATH=backend .venv311/bin/alembic -c alembic.ini upgrade head

# 5. Configure env
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials (see Section 6)

# 6. Start backend
PYTHONPATH=backend .venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# Logs → /tmp/vn-accounting-backend.log (when started with that redirection)

# 7. Web (separate terminal)
cd web
cp .env.local.example .env.local  # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm install --legacy-peer-deps
npm run dev
# → http://localhost:3001

# 8. Docker Compose (alternative)
cd vn-accounting
cp .env.example .env  # configure JWT_SECRET_KEY at minimum
docker compose up --build
# Backend: http://localhost:8000
# Web: http://localhost:3001
# Postgres: localhost:55432
```

### Test Credentials (local dev only)
```bash
# Register a new account at POST /api/v1/auth/register
# Or use seeded test user:
email:    gbert+e2e@test.com
password: TestPass123456!
company:   Test Company LLC
tax_code:  0123456789
```

---

## 10. Known Limitations

| # | Limitation | Impact | Workaround |
|---|-----------|--------|-----------|
| 1 | `documents.ocr_pages` JSONB column uses mixed string/number types from Google Vision | API serialization may be inconsistent | Normalize types before serialization |
| 2 | `journal_entries` and `chart_of_accounts` tables exist but have no UI | CIT calculations require manual JE entry | Populate via direct DB inserts or future API |
| 3 | Password reset generates tokens but does not send real email | Users cannot reset passwords via email | Operator can reset directly in DB |
| 4 | Invoice list has no filters (date, seller, VAT rate, GDT status) | Hard to find specific invoices | Use API directly with query params; UI filter is ROADMAP |
| 5 | PDF VAT export returns HTTP 501 | Tax reports cannot be exported as PDF | Use XLSX export (working) |
| 6 | Mobile Flutter app has dashboard/login stubs only | No full mobile workflow | Scanner-first MVP is functional |
| 7 | No live GDT endpoint — service degrades gracefully | E-invoice verification not available without credentials | Configure GDT env vars for production |
| 8 | `CELERY_TASK_ALWAYS_EAGER=1` in local dev | Background tasks run synchronously | Normal for dev; Celery worker needed for production scale |
| 9 | No rate limiting on upload or auth endpoints | Potential abuse | Implement at production deployment layer |
| 10 | Duplicate upload retry only handles `FAILED` and `PENDING` status | Other intermediate statuses not handled | Manual DB reset available as escape hatch |

---

## 11. Performance Benchmarks

Based on local testing with `v2-test-invoice.pdf` (single-page PDF, ~2KB):

| Metric | Value |
|--------|-------|
| Google Vision OCR (1 page) | ~1,238 ms |
| DeepSeek extraction (from OCR text) | ~1,500–2,500 ms |
| Full pipeline (upload → extracted) | ~3,000–4,000 ms |
| PaddleOCR OCR (CPU, 1 page) | ~2,000–4,000 ms |
| Local storage upload | ~50–100 ms |
| JWT token generation | ~10 ms |
| Document GET (cached session) | ~20 ms |

**Concurrency:** Local dev server is single-worker (`uvicorn --reload`). Production should use multiple workers (`uvicorn --workers 4`).

---

## 12. Files Changed This Audit Cycle

| File | Change | Commit |
|------|--------|--------|
| `backend/app/api/routes/documents.py` | Duplicate upload retry now handles `PENDING` status (was only `FAILED`) | [NEW COMMIT] |
| `backend/app/services/ocr/google_vision.py` | Fixed dedented block causing syntax error; fixed `s.symbol.text` → `s.text` | [NEW COMMIT] |
| `backend/app/services/extraction/claude_extractor.py` | Added DeepSeek as primary LLM provider; graceful fallback chain | [NEW COMMIT] |
| `backend/app/core/config.py` | Added `LLM_PROVIDER`, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` settings | [NEW COMMIT] |
| `backend/app/services/storage/r2_service.py` | Added placeholder-check guard for R2 config detection | [NEW COMMIT] |
| `backend/alembic/env.py` | `String(64)` → `VARCHAR(64)` for PostgreSQL compatibility | [NEW COMMIT] |
| `docker-compose.yml` | Added `?sslmode=disable` to `DATABASE_URL_SYNC`; switched web to `Dockerfile.dev` | [NEW COMMIT] |
| `web/Dockerfile` | Changed `npm ci` → `npm install --legacy-peer-deps`; removed premature `NODE_ENV=production` | [NEW COMMIT] |

---

## 13. Remaining Production Blockers

These must be resolved before production deployment:

| Priority | Blocker | Owner |
|---------|---------|-------|
| 🔴 CRITICAL | `JWT_SECRET_KEY` is hardcoded as `dev-jwt-secret` in `docker-compose.yml` | Operator |
| 🔴 CRITICAL | `DATABASE_URL` credentials in `.env` (vn_accounting:TestPass123!) are weak | Operator |
| 🔴 CRITICAL | No R2 storage configured — all files go to local filesystem which is ephemeral in Coolify | Operator |
| 🔴 CRITICAL | No persistent volume configured for `documents` storage in Coolify | Operator |
| 🟡 HIGH | No Celery worker — `CELERY_TASK_ALWAYS_EAGER=1` means all processing blocks the request in prod | Operator |
| 🟡 HIGH | No rate limiting on upload or auth endpoints | Operator |
| 🟡 HIGH | GDT e-invoice credentials not configured | Operator |
| 🟡 HIGH | No HTTPS/TLS in local dev | Normal for dev; resolve at deploy |
| 🟢 MEDIUM | Invoice list has no filters | ROADMAP |
| 🟢 MEDIUM | PDF VAT export returns 501 | ROADMAP |
| 🟢 MEDIUM | No email sending for password reset | ROADMAP |

---

## 14. Commit Hash

To be filled in after `git push`:

```
COMMIT=<hash>
```

Run this to get it:
```bash
cd /Users/gilbertneo/Desktop/My\ Apps/Vietnam\ Accounting\ App/vn-accounting
git log -1 --format='%H %s'
```
