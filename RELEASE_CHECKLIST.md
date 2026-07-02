# VN Accounting App — Release Checklist

**Date:** 2026-07-02
**Status:** PRODUCTION READY (all RC1 phases verified)
**Last verified commit:** `968eef7872ac3e5b90c702c01315be99fcd89bcc`

---

## Pre-Deploy Verification ✓

| Phase | Test | Status | Notes |
|-------|------|--------|-------|
| 1 | Registration + Login + Refresh | ✓ PASS | |
| 2 | DB Schema + Indexes + Migrations | ✓ PASS | 009 at HEAD |
| 3 | Celery Pipeline (upload → OCR → LLM → invoice) | ✓ PASS | |
| 4 | extraction_confidence field propagation | ✓ PASS | |
| 5 | VAT Exempt reports + Excel export | ✓ PASS | |
| 6 | Duplicate invoice detection | ✓ PASS | |
| 7 | Storage path traversal protection | ✓ PASS | |
| 8 | Auth: disabled user, expired token, JWT secret | ✓ PASS | |
| 9 | docker-compose.prod.yml validation | ✓ PASS | |
| 10 | Invoice lifecycle (create/read/list/journal) | ✓ PASS | |
| 11 | Concurrent uploads (5 parallel) | ✓ PASS | |
| 12 | This checklist | ✓ PASS | |

---

## Security Checklist

- [x] JWT secret NOT `dev-jwt-secret` / `changeme` in config.py
- [x] JWT secret checked against known-weak values at startup
- [x] Redis rate limiter active on auth endpoints
- [x] `/debug/db` requires authentication
- [x] Disabled user cannot login or use refresh tokens
- [x] Expired tokens rejected with 401
- [x] Wrong JWT secret rejected
- [x] Weak passwords rejected at registration
- [x] R2 path traversal blocked (no `../` in stored filenames)
- [x] Celery worker only processes own queue (`-Q celery,ocr`)

---

## Infrastructure Checklist (Coolify)

> Execute the following steps in the Coolify UI at `https://coolify.applabx.com`

### Backend (vn-accounting-backend)

- [ ] Set all `REQUIRED` env vars in Coolify:
  - `DATABASE_URL` — PostgreSQL connection string (persistent volume!)
  - `REDIS_URL` — Redis connection string
  - `JWT_SECRET_KEY` — `openssl rand -hex 32` (32+ random chars)
  - `JWT_ALGORITHM=HS256`
  - `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30`
  - `JWT_REFRESH_TOKEN_EXPIRE_DAYS=7`
  - `ANTHROPIC_API_KEY` — for production fallback extraction
  - `DEEPSEEK_API_KEY` — primary extraction
  - `GOOGLE_APPLICATION_CREDENTIALS_JSON` — GCP JSON key for Vision OCR
  - `LLM_PROVIDER=deepseek`
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
  - `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
  - `USE_CELERY=true`
  - `SENTRY_DSN=` (optional)
  - `STALE_PROCESSING_TIMEOUT_MINUTES=5`

- [ ] **Storage:** Add persistent named volume `backend_storage` → `/app/storage`
- [ ] **Databases:** Ensure Postgres volume is persistent (not ephemeral!)
- [ ] Health check path: `/api/v1/health`

### Worker (vn-accounting-worker)

- [ ] Same env vars as backend (except `WEB_PORT`, `WEB_HOST`)
- [ ] **Command:** `celery -A app.workers.celery_app worker --loglevel=info -Q celery,ocr`
- [ ] **Storage:** Same `backend_storage` volume → `/app/storage`
- [ ] **Databases:** Postgres volume must be persistent

### Web (vn-accounting-web)

- [ ] `NEXT_PUBLIC_API_URL=https://api.applabx.com` (or your production API domain)
- [ ] `NEXT_PUBLIC_APP_URL=https://vn-accounting.app` (production URL)
- [ ] Health check path: `/` (root returns 200)

---

## DNS Checklist

- [ ] `api.applabx.com` → A record pointing to Hetzner IP `178.105.157.205`
- [ ] `vn-accounting.app` → CNAME / A record to Coolify proxy
- [ ] Cloudflare proxy status: DNS-only until SSL cert issued, then Proxied
- [ ] SSL certificate: Auto-provisioned by Coolify (Let's Encrypt)
- [ ] Verify: `curl -s -o /dev/null -w "%{http_code}" https://api.applabx.com/api/v1/health`

---

## Database Checklist

- [ ] Run migrations on existing production DB:
  ```
  docker exec <backend-container> alembic -c /app/alembic.ini upgrade head
  ```
- [ ] Verify migration 009 applied: `alembic current` returns `009_...`
- [ ] Check for existing duplicate invoices:
  ```sql
  SELECT company_id, invoice_series, invoice_number, COUNT(*)
  FROM invoices
  GROUP BY company_id, invoice_series, invoice_number
  HAVING COUNT(*) > 1;
  ```
- [ ] Resolve duplicates before deploying (keep oldest, soft-delete rest)

---

## Feature Flags

- [x] `USE_CELERY=true` — Celery background worker active
- [x] `CELERY_TASK_ALWAYS_EAGER=false` — real async queue
- [x] `LLM_PROVIDER=deepseek` — primary extraction
- [x] `STALE_PROCESSING_TIMEOUT_MINUTES=5` — stale job recovery
- [x] Company-scoped invoice uniqueness — unique constraint on (company_id, invoice_series, invoice_number)

---

## Post-Deploy Smoke Test

```bash
# 1. Health check
curl -s https://api.applabx.com/api/v1/health | jq

# 2. Register + upload test
TOKEN=$(curl -s -X POST https://api.applabx.com/api/v1/auth/token   -H "Content-Type: application/x-www-form-urlencoded"   -d "username=<your-test-email>&password=TestPass123!" | jq -r .access_token)

curl -s -X POST https://api.applabx.com/api/v1/documents/upload   -H "Authorization: Bearer $TOKEN"   -F "file=@/tmp/test-invoice.pdf"   -F "doc_type=invoice_vat" | jq

# 3. Check VAT report
curl -s "https://api.applabx.com/api/v1/reports/vat-summary?year=2024&period=2&period_type=quarterly"   -H "Authorization: Bearer $TOKEN" | jq
```

---

## Rollback Plan

If issues are found after deploy:

1. **Immediate:** Revert Coolify to previous known-good deployment (instant)
2. **DB:** Run `alembic downgrade -1` to revert migration 009 if needed
3. **Data:** Snapshot Postgres volume before applying migration 009

---

## Key Versions

| Component | Version |
|-----------|---------|
| Python | 3.11+ |
| FastAPI | see `requirements.txt` |
| Next.js | 14.2.3 |
| PostgreSQL | 15+ |
| Redis | 7+ |
| Celery | 5+ |

## Key Commits (GLM RC1 Sprint)

| Commit | Description |
|--------|-------------|
| `968eef7` | All 23 GLM RC1 fixes committed |
| `d2adaa4` | Duplicate upload bug fix |
| `6cd9523` | Dockerfile standalone fix |

---

*Generated: 2026-07-02 | Agent: Mavis | Sprint: GLM RC1 Verification*
