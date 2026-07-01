#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found. Copy .env.example to .env and fill secrets first." >&2
  exit 1
fi

docker compose --profile full pull || true
docker compose --profile full build
docker compose --profile full up -d
docker compose exec -T backend alembic upgrade head
docker compose --profile full ps
