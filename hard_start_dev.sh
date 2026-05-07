#!/usr/bin/env bash
set -euo pipefail

# Dev запуск: полностью чистит локальный Docker, затем заново собирает PostgreSQL + MinIO + backend + frontend.

docker compose -f docker-compose.dev.yml down --remove-orphans --volumes --rmi all || true

containers="$(docker ps -aq)"
if [ -n "$containers" ]; then
  docker rm -f $containers
fi

docker system prune -af --volumes
docker builder prune -af

docker compose -f docker-compose.dev.yml up -d --build --force-recreate
