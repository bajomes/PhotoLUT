#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_BRANCH="feat/pixel7-video-hdr-4k30"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: run this script inside the PhotoLUT Git repository." >&2
  exit 1
}
cd "$ROOT"

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
  echo "ERROR: wrong branch: $CURRENT_BRANCH" >&2
  echo "Switch to the feature branch first:" >&2
  echo "  git fetch origin $EXPECTED_BRANCH" >&2
  echo "  git switch --track origin/$EXPECTED_BRANCH" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is not clean. Commit or stash local changes before updating." >&2
  exit 1
fi

echo "Updating $EXPECTED_BRANCH from origin..."
git fetch origin "$EXPECTED_BRANCH"
git pull --ff-only origin "$EXPECTED_BRANCH"

echo "Building and recreating PhotoLUT from commit $(git rev-parse --short HEAD)..."
docker compose up --build --force-recreate --detach

echo "Waiting for the local service..."
for attempt in $(seq 1 40); do
  if curl --fail --silent http://127.0.0.1:8000/openapi.json >/dev/null; then
    break
  fi
  if [[ "$attempt" -eq 40 ]]; then
    echo "ERROR: PhotoLUT did not become healthy at http://127.0.0.1:8000." >&2
    docker compose logs --tail=100
    exit 1
  fi
  sleep 2
done

HTML="$(curl --fail --silent http://127.0.0.1:8000/)"
if ! grep -Fq 'HDR INSPECTION &amp; EXPORT' <<<"$HTML" && ! grep -Fq 'HDR INSPECTION & EXPORT' <<<"$HTML"; then
  echo "ERROR: the running UI does not contain the HDR inspection panel." >&2
  echo "The container may be serving a different checkout or image." >&2
  exit 1
fi

OPENAPI="$(curl --fail --silent http://127.0.0.1:8000/openapi.json)"
if ! grep -Fq '/api/video/preserve-hdr' <<<"$OPENAPI"; then
  echo "ERROR: the running API does not expose /api/video/preserve-hdr." >&2
  exit 1
fi

echo "OK: PhotoLUT is running the HDR feature branch."
echo "Commit: $(git rev-parse HEAD)"
echo "URL: http://127.0.0.1:8000/"
echo "API: http://127.0.0.1:8000/docs"
