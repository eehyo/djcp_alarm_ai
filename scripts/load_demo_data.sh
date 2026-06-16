#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

: "${PSQL_URL:?Set PSQL_URL in .env or the environment}"
PSQL_BIN="${PSQL_BIN:-psql}"

"$PSQL_BIN" -X -v ON_ERROR_STOP=1 "$PSQL_URL" -f "$PROJECT_ROOT/data/demo_seed.sql"
