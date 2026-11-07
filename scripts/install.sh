#!/usr/bin/env bash
set -Eeuo pipefail
if ! command -v docker >/dev/null 2>&1; then echo "Docker is required. Install Docker Desktop or Engine first." >&2; exit 1; fi
if ! command -v curl >/dev/null 2>&1; then echo "curl is required for the HTTP readiness check." >&2; exit 1; fi
if ! docker compose version >/dev/null 2>&1; then echo "Docker Compose v2 plugin is required." >&2; exit 1; fi
if ! docker info >/dev/null 2>&1; then echo "Docker daemon is not running or is inaccessible." >&2; exit 1; fi
echo "Building and starting PhotoLUT..."
docker compose up --build -d
URL="${PHOTOLUT_URL:-http://127.0.0.1:8000}"
for attempt in $(seq 1 45); do
  if command -v curl >/dev/null 2>&1 && curl --fail --silent "$URL/" >/dev/null; then
    echo "PhotoLUT is ready: $URL"; exit 0
  fi
  sleep 2
done
echo "PhotoLUT did not become ready at $URL. Recent container logs:" >&2
docker compose logs --tail=100 >&2
exit 1
