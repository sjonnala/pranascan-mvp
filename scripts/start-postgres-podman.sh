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

if podman container exists "$CONTAINER_NAME"; then
  if [ "$(podman inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" = "true" ]; then
    echo "PostgreSQL container '$CONTAINER_NAME' is already running."
  else
    podman start "$CONTAINER_NAME" >/dev/null
    echo "Started existing PostgreSQL container '$CONTAINER_NAME'."
  fi
else
  podman volume create "$VOLUME_NAME" >/dev/null
  podman run -d \
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
