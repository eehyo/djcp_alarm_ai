#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 migrations/NNN_description.sql" >&2
  exit 1
fi

MIGRATION_PATH="$1"
if [[ "$MIGRATION_PATH" != /* ]]; then
  MIGRATION_PATH="$PROJECT_ROOT/$MIGRATION_PATH"
fi

if [[ ! -f "$MIGRATION_PATH" || "$MIGRATION_PATH" != "$PROJECT_ROOT"/migrations/*.sql ]]; then
  echo "Migration must be a SQL file directly under $PROJECT_ROOT/migrations" >&2
  exit 1
fi

: "${PSQL_URL:?Set PSQL_URL in .env or the environment}"
PSQL_BIN="${PSQL_BIN:-psql}"

"$PSQL_BIN" -X -v ON_ERROR_STOP=1 "$PSQL_URL" -f "$MIGRATION_PATH"
echo "Applied migration: $MIGRATION_PATH"
