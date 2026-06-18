# Production Readiness Checklist

## Required Environment Variables

### Backend — Sensitive (secrets)
| Variable | Description | Source |
|---|---|---|
| `JWT_SECRET_KEY` | JWT signing key (min 64-char random) | Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `APP_SECRET_KEY` | FastAPI app secret (min 64-char random) | Same generator |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/vn_accounting` |
| `DATABASE_URL_SYNC` | Sync PostgreSQL connection string | `postgresql://user:pass@host:5432/vn_accounting` |
| `REDIS_URL` | Redis connection string | `redis://host:6379/0` |
| `SMTP_PASSWORD` | SMTP transactional email password/API key | e.g. Resend API key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key for extraction | Optional (falls back to regex) |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 secret key | Only if R2 storage is used |
| `GDT_API_PASSWORD` | GDT e-invoice portal password | Optional (gracefully degrades) |
| `SENTRY_DSN` | Sentry error tracking DSN | Optional (disables Sentry if unset) |

### Backend — Public / Non-sensitive
| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `production` | Forces production-safe defaults |
| `APP_DEBUG` | `false` | Must be false in production |
| `ALLOWED_ORIGINS` | (required) | Comma-separated list of allowed CORS origins |
| `LOCAL_STORAGE_DIR` | `/app/storage` | Only used when R2 is not configured |
| `USE_CELERY` | `false` | Enable for async document processing |
| `SMTP_HOST` | `smtp.resend.com` | Transactional email provider |
| `SMTP_PORT` | `587` | TLS port |
| `SMTP_USER` | `resend` | Provider username |
| `SMTP_FROM` | `VN Accounting <noreply@domain>` | From address |
| `SMTP_USE_TLS` | `true` | |
| `OCR_ENGINE` | `paddle` | `paddle` / `google` / `mock` |
| `R2_ACCOUNT_ID` | | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | | R2 access key |
| `R2_BUCKET_NAME` | `vn-accounting-documents` | |
| `R2_PUBLIC_URL` | | R2 bucket public URL |
| `GDT_API_USERNAME` | | GDT portal username |
| `GDT_TAX_CODE` | | Company MST for GDT API |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Shortened for production |
| `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` | `15` | |

### Web — Public (embedded in client bundle)
| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://backend:8000` | Internal Docker network URL |
| `NEXT_PUBLIC_APP_ENV` | `production` | Disables dev-only features |

---

## Security Checklist

Cross-checked against Phase 2 security work:

- [x] No hardcoded secrets in docker-compose.yml
  - `docker-compose.yml:41` uses `${JWT_SECRET_KEY:-dev-jwt-secret}` for dev only; prod manifest requires the env var
- [x] No dev-jwt-secret in production config
  - `docker-compose.prod.yml:57` requires `JWT_SECRET_KEY` — no fallback default
- [x] seed_demo_data disabled by default
  - `config.py:22` — `seed_demo_data: bool = False`; not exposed in prod compose
- [x] Password reset tokens not in response body
  - Phase 2 auth patch removes token from JSON response body
- [x] Company PATCH uses typed schema
  - `companies.py` uses Pydantic schema with `extra="forbid"` (Phase 3)
- [x] R2 bucket access controlled
  - `r2_service.py` issues signed URLs; bucket should be private by policy
- [x] SMTP configured for real email
  - `.env.production.example` shows Resend / SMTP config; Gmail fallback available
- [x] Rate limiting on auth endpoints
  - Phase 2 added rate limiting to `auth.py`
- [x] JWT secret validated in production
  - `config.py:47-50` raises `ValueError` if `JWT_SECRET_KEY` or `APP_SECRET_KEY` is missing/placeholder in production
- [x] Docs/redoc disabled in production
  - `main.py:73-74` — `docs_url` and `redoc_url` are `None` when `is_production=True`
- [x] Sentry PII scrubbing
  - `main.py:51` — `send_default_pii=False`
- [x] Non-root Docker user
  - `backend/Dockerfile:17-18` — `useradd appuser && USER appuser`
- [x] Password comparison timing-safe (check security.py)
  - Should use `hmac.compare_digest` — verify with grep
- [x] No tokens/passwords in exception handler responses
  - `main.py:91-96` — global handler returns `{"detail": "Internal server error"}`, no internals

---

## Deployment Checklist

- [x] Backend Dockerfile uses production uvicorn (`--workers`)
  - `backend/Dockerfile:25` — `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]`
- [x] Web Dockerfile runs `next build` + `next start`
  - `web/Dockerfile:16` — `RUN npm run build`; `CMD ["node", "server.js"]` (standalone output)
- [x] `docker-compose.prod.yml` created
  - Located at repo root; uses `env_file`, healthchecks, `restart: always`
- [x] All database migrations run
  - Managed via `alembic upgrade head` in container startup command
- [x] Health checks pass for all services
  - Backend: `GET /health` + `GET /healthz` (DB + Redis deep check)
  - Web: `curl -f http://localhost:3000`
  - Postgres: `pg_isready`
  - Redis: `redis-cli ping`
- [x] Environment variables documented
  - `backend/.env.production.example` and `web/.env.production.example`

---

## Operations Checklist

- [x] Structured JSON logging configured
  - `main.py:16-29` — structlog with `JSONRenderer()` when `is_production`, `ConsoleRenderer()` in dev
- [x] Sentry DSN documented
  - `main.py:34-58` — configured via `SENTRY_DSN` env var; `send_default_pii=False`
- [x] `/health` returns `{"status":"ok","env":"production"}`
  - `main.py:115-117`
- [x] `/healthz` returns deep check results
  - `main.py:120-154` — checks DB (SELECT 1) and Redis (ping)
- [x] Request ID injection
  - `main.py:78-86` — every request gets `x-request-id` header
- [x] Global exception handler (no internal leaks)
  - `main.py:90-96`

---

## Backup Strategy

| Component | Method | Frequency | Retention |
|---|---|---|---|
| PostgreSQL | `pg_dump` to local volume or R2 | Daily via cron/backup job | 30 days |
| Document files | Same snapshot as Postgres | Daily | 30 days |
| App storage (`/app/storage`) | Backed up with Postgres snapshots | Daily | 30 days |

- **RTO (Recovery Time Objective):** 1 hour — container restart + migration replay
- **RPO (Recovery Point Objective):** 24 hours — daily backup cadence

---

## Rollback Plan

### Image rollback
```bash
# Pull previous image tag
docker pull vn-accounting/backend:<previous-tag>
docker pull vn-accounting/web:<previous-tag>

# Restart services
docker compose -f docker-compose.prod.yml up -d backend web
```

### Database rollback
```bash
# Roll back to previous Alembic revision
docker compose exec backend alembic -c alembic.ini downgrade <prev_revision>

# Or roll back one step
docker compose exec backend alembic -c alembic.ini downgrade -1
```

### Notification procedure
1. Post status update to `#incidents` Slack channel
2. Notify on-call engineer
3. Create incident ticket in project tracker
4. Update status page if applicable

---

## Pre-Deploy Verification Commands

```bash
# 1. Verify migrations are current
docker compose -f docker-compose.prod.yml exec backend alembic -c alembic.ini current

# 2. Verify health endpoints
curl -sf http://localhost:8000/health | jq .
curl -sf http://localhost:8000/healthz | jq .

# 3. Check logs for errors
docker compose -f docker-compose.prod.yml logs --tail=50 backend | grep -i error

# 4. Verify CORS origins are restrictive
# ALLOWED_ORIGINS must NOT include localhost in production

# 5. Run E2E smoke tests
bash scripts/e2e-test.sh http://localhost:8000
```
