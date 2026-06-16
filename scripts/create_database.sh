#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-djcp_alarm_ai}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PSQL_BIN="${PSQL_BIN:-psql}"
CREATEDB_BIN="${CREATEDB_BIN:-createdb}"

if [[ ! "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "Invalid DB_NAME: $DB_NAME" >&2
  exit 1
fi

if "$PSQL_BIN" -X -Atq -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
  -c "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
  echo "Database already exists: $DB_NAME" >&2
  echo "No changes were made." >&2
  exit 1
fi

"$CREATEDB_BIN" -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" --owner="$PGUSER" "$DB_NAME"

if ! "$PSQL_BIN" -X -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$DB_NAME" \
  -f "$PROJECT_ROOT/migrations/000_create_operational_schema.sql" \
  -f "$PROJECT_ROOT/migrations/001_ai_tag_description.sql"; then
  echo "Database was created, but schema setup failed: $DB_NAME" >&2
  echo "Inspect and remove the incomplete database manually before retrying." >&2
  exit 1
fi

echo "Created database: $DB_NAME"
echo "Set these values in .env:"
echo "DATABASE_URL=postgresql+psycopg://$PGUSER@${PGHOST}:${PGPORT}/${DB_NAME}"
echo "PSQL_URL=postgresql://$PGUSER@${PGHOST}:${PGPORT}/${DB_NAME}"
