#!/usr/bin/env bash
set -euo pipefail

# Обычный запуск: полностью чистит локальный Docker, затем заново собирает backend + frontend.
# PostgreSQL и S3 берутся из .env.

docker compose down --remove-orphans --volumes --rmi all || true

containers="$(docker ps -aq)"
if [ -n "$containers" ]; then
  docker rm -f $containers
fi

docker system prune -af --volumes
docker builder prune -af

docker compose up -d --build --force-recreate
