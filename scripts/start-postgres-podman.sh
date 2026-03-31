#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${PRANASCAN_DB_CONTAINER:-pranascan-postgres}"
VOLUME_NAME="${PRANASCAN_DB_VOLUME:-pranascan-postgres-data}"
DB_NAME="${PRANASCAN_DB_NAME:-pranascan}"
DB_USER="${PRANASCAN_DB_USER:-pranascan}"
DB_PASSWORD="${PRANASCAN_DB_PASSWORD:-pranascan_dev_password}"
HOST_PORT="${PRANASCAN_DB_PORT:-5432}"
IMAGE="${PRANASCAN_DB_IMAGE:-docker.io/library/postgres:16-alpine}"

if ! command -v podman >/dev/null 2>&1; then
  echo "podman is not installed or not on PATH." >&2
  exit 1
fi

run_podman() {
  local output
  if ! output=$("$@" 2>&1); then
    echo "$output" >&2
    if [[ "$output" == *"invalid username/password"* ]] || [[ "$output" == *"unauthorized"* ]]; then
      echo >&2
      echo "Podman appears to have cached invalid docker.io credentials." >&2
      echo "Try one of these fixes, then rerun this script:" >&2
      echo "  podman logout docker.io" >&2
      echo "  podman login docker.io" >&2
    fi
    exit 1
  fi
  printf '%s\n' "$output"
}

if podman container exists "$CONTAINER_NAME"; then
  if [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" = "true" ]; then
    echo "PostgreSQL container '$CONTAINER_NAME' is already running."
  else
    run_podman podman start "$CONTAINER_NAME" >/dev/null
    echo "Started existing PostgreSQL container '$CONTAINER_NAME'."
  fi
else
  if ! podman volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    run_podman podman volume create "$VOLUME_NAME" >/dev/null
  fi
  run_podman podman run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_DB="$DB_NAME" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="$DB_PASSWORD" \
    -p "${HOST_PORT}:5432" \
    -v "${VOLUME_NAME}:/var/lib/postgresql/data" \
    "$IMAGE" >/dev/null
  echo "Created and started PostgreSQL container '$CONTAINER_NAME'."
fi

echo
echo "Connection details:"
echo "  host: localhost"
echo "  port: ${HOST_PORT}"
echo "  db:   ${DB_NAME}"
echo "  user: ${DB_USER}"
echo
echo "DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:${HOST_PORT}/${DB_NAME}"
