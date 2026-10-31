#!/usr/bin/env bash
# Deploy one environment from a git ref.
#   ./deploy/deploy.sh staging main
#   ./deploy/deploy.sh production v1.0.0
# Rollback is the same command with the previous tag.
set -euo pipefail

APP_ENV="${1:?usage: deploy.sh <production|staging> <git-ref>}"
REF="${2:?usage: deploy.sh <production|staging> <git-ref>}"
case "$APP_ENV" in production | staging) ;; *) echo "unknown environment: $APP_ENV" >&2; exit 2 ;; esac

cd "$(dirname "$0")/.."
ENV_FILE="/srv/hrweb/$APP_ENV/.env"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE" >&2; exit 2; }

compose() {
  APP_ENV="$APP_ENV" ENV_FILE="$ENV_FILE" IMAGE_TAG="$REF" \
    docker compose -f compose.prod.yml --env-file "$ENV_FILE" -p "hrweb-$APP_ENV" "$@"
}

echo "==> Fetching $REF"
git fetch --tags --prune origin
# A branch name must mean the latest pushed commit, not a stale local copy
git checkout --quiet --detach "origin/$REF" 2>/dev/null || git checkout --quiet --detach "$REF"

echo "==> Building image"
compose build

echo "==> Migrating and restarting"
compose up -d --remove-orphans

echo "==> Waiting for /healthz"
PORT="$(grep -E '^WEB_PORT=' "$ENV_FILE" | cut -d= -f2)"
for _ in $(seq 1 40); do
  if curl -fsS -H 'Host: localhost' -H 'X-Forwarded-Proto: https' \
    "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    echo "==> $APP_ENV is healthy on $REF ($(git rev-parse --short HEAD))"
    exit 0
  fi
  sleep 3
done

echo "==> Health check FAILED. Latest logs:" >&2
compose logs --tail 40 web >&2
exit 1
