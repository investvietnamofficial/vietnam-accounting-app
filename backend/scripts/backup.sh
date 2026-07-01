#!/usr/bin/env bash
# =============================================================================
# VN Accounting — Production Backup Script
# =============================================================================
# Usage:
#   ./scripts/backup.sh                          # local backup only
#   ./scripts/backup.sh --upload-r2              # backup + upload to R2
#   ./scripts/backup.sh --keep 7                 # keep last N local backups
#
# Required env vars (set in Coolify or .env):
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME  (for --upload-r2)
#
# Cron example (run daily at 03:00 UTC):
#   0 3 * * * cd /app && ./scripts/backup.sh --upload-r2 --keep 7 >> /var/log/vn-accounting-backup.log 2>&1
# =============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_LOCAL="${KEEP_LOCAL:-7}"
UPLOAD_R2="false"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMPFILE="${BACKUP_DIR}/vn_accounting_${TIMESTAMP}.sql.gz"

# ── Args ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --upload-r2)  UPLOAD_R2="true"; shift ;;
    --keep)       KEEP_LOCAL="$2"; shift 2 ;;
    *)            echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [[ -z "${POSTGRES_HOST:-}" ]]; then
  echo "ERROR: POSTGRES_HOST is not set." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Starting backup to ${DUMPFILE}"

# ── 1. pg_dump ────────────────────────────────────────────────────────────────
# PGPASSWORD avoids the password prompt; host/port/user/db come from env
export PGPASSWORD="${POSTGRES_PASSWORD:-}"
pg_dump \
  --host "${POSTGRES_HOST}" \
  --port "${POSTGRES_PORT:-5432}" \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-acl \
  --file "${DUMPFILE%.gz}"  # pg_dump custom format (no .gz suffix)

# Compress the plain-text format backup
gzip -9 "${DUMPFILE%.gz}" 2>/dev/null || true
DUMPFILE="${DUMPFILE}"  # already set above

BACKUP_SIZE=$(du -h "${DUMPFILE}" | cut -f1)
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] pg_dump done (${BACKUP_SIZE}): ${DUMPFILE}"

# ── 2. Optional R2 upload ────────────────────────────────────────────────────
if [[ "${UPLOAD_R2}" == "true" ]]; then
  if [[ -z "${R2_ACCOUNT_ID:-}" || -z "${R2_ACCESS_KEY_ID:-}" ]]; then
    echo "WARN: R2 credentials not set — skipping R2 upload." >&2
  else
    R2_KEY="backups/$(basename "${DUMPFILE}")"
    # Use AWS CLI with R2 S3-compatible API
    AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}" \
    AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}" \
    aws s3 cp \
      --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestaging.com" \
      "${DUMPFILE}" \
      "s3://${R2_BUCKET_NAME}/${R2_KEY}"
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Uploaded to R2: ${R2_KEY}"
  fi
fi

# ── 3. Prune old local backups ───────────────────────────────────────────────
if [[ "${KEEP_LOCAL}" != "0" ]]; then
  # Keep the N most recent .sql.gz files, delete the rest
  cd "${BACKUP_DIR}"
  # shellcheck disable=SC2015
  ls -t vn_accounting_*.sql.gz 2>/dev/null \
    | tail -n +$((KEEP_LOCAL + 1)) \
    | xargs rm -f -- 2>/dev/null || true
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Pruned old backups (kept ${KEEP_LOCAL})"
fi

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Backup complete."
