#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://agent:changeme@localhost:5432/agentdb}"
MIGRATIONS_DIR="$(dirname "$0")/../infra/postgres/migrations"

# Convert asyncpg URL to psql-compatible URL
PSQL_URL="${DB_URL/postgresql+asyncpg/postgresql}"

echo "Running migrations from $MIGRATIONS_DIR"
for f in "$MIGRATIONS_DIR"/*.sql; do
  echo "  Applying $f..."
  psql "$PSQL_URL" -f "$f"
done
echo "Migrations complete."
