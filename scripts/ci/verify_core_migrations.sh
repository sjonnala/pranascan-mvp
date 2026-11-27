#!/usr/bin/env bash
# Applies service-core's Flyway scripts (V1..V10) to an empty Postgres 16 database with
# plain psql, seeding legacy rows after V7, then probes backfills, legacy INSERT
# compatibility and the new CHECK guards. Uses libpq env vars (PGHOST, PGUSER, ...).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS="$ROOT/service-core/src/main/resources/db/migration"
PROBES="$ROOT/scripts/ci/core_migration_probes"
PSQL=(psql -v ON_ERROR_STOP=1 -X -q -t)

apply() {
  echo "apply $(basename "$1")"
  "${PSQL[@]}" --single-transaction -f "$1"
}

mapfile -t scripts < <(ls "$MIGRATIONS"/V*__*.sql | sort -V)
for f in "${scripts[@]}"; do
  v="$(basename "$f" | sed -E 's/^V([0-9]+)__.*/\1/')"
  apply "$f"
  if [[ "$v" == "7" ]]; then
    echo "seed legacy rows (rev-1 shapes, before V8)"
    "${PSQL[@]}" --single-transaction -f "$PROBES/01_seed_legacy_rows.sql"
  fi
done

echo "probe backfills and INSERT compatibility"
"${PSQL[@]}" --single-transaction -f "$PROBES/02_assert_after_v10.sql"

echo "probe CHECK guards (each statement must be rejected)"
fail=0
while IFS='|' read -r constraint stmt; do
  [[ -z "$constraint" || "$constraint" == --* ]] && continue
  if err="$("${PSQL[@]}" -c "$stmt" 2>&1 >/dev/null)"; then
    echo "  NOT REJECTED: $stmt"; fail=1
  elif [[ "$err" != *"\"$constraint\""* ]]; then
    echo "  REJECTED FOR ANOTHER REASON (wanted $constraint): $err"; fail=1
  else
    echo "  rejected by $constraint"
  fi
done < "$PROBES/03_must_be_rejected.sql"

[[ $fail -eq 0 ]] || { echo "CHECK guard probes failed"; exit 1; }
echo "OK: V1..V10 applied; backfills, legacy INSERTs and CHECK guards verified"
