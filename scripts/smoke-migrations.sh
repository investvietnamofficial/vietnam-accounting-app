#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

export PYTHONPATH="${ROOT_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
SMOKE_DATABASE_NAME="${SMOKE_DATABASE_NAME:-vn_accounting_migration_smoke}"

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://vn_accounting:vn_accounting_dev@localhost:55432/${SMOKE_DATABASE_NAME}}"
export DATABASE_URL_SYNC="${DATABASE_URL_SYNC:-postgresql://vn_accounting:vn_accounting_dev@localhost:55432/${SMOKE_DATABASE_NAME}}"

ALEMBIC_BIN="${ALEMBIC_BIN:-${ROOT_DIR}/.venv311/bin/alembic}"
if [[ ! -x "${ALEMBIC_BIN}" ]]; then
  ALEMBIC_BIN="$(command -v alembic || true)"
fi

if [[ -z "${ALEMBIC_BIN}" ]]; then
  echo "Unable to find alembic. Set ALEMBIC_BIN or install backend dependencies." >&2
  exit 1
fi

cleanup() {
  docker compose exec -T postgres psql -U vn_accounting -d postgres \
    -c "DROP DATABASE IF EXISTS ${SMOKE_DATABASE_NAME};" >/dev/null 2>&1 || true
  docker compose stop postgres >/dev/null 2>&1 || true
}

trap cleanup EXIT

docker compose up -d postgres

for _ in {1..30}; do
  if docker compose exec -T postgres pg_isready -U vn_accounting >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker compose exec -T postgres psql -U vn_accounting -d postgres \
  -c "DROP DATABASE IF EXISTS ${SMOKE_DATABASE_NAME};" >/dev/null
docker compose exec -T postgres psql -U vn_accounting -d postgres \
  -c "CREATE DATABASE ${SMOKE_DATABASE_NAME};" >/dev/null

cd backend
"${ALEMBIC_BIN}" -c alembic.ini upgrade head
"${ALEMBIC_BIN}" -c alembic.ini downgrade base
"${ALEMBIC_BIN}" -c alembic.ini upgrade head
