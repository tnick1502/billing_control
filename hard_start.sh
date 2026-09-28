#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Безопасный полный перезапуск production-стека.
# Скрипт намеренно НЕ удаляет Docker volumes, образы и контейнеры других проектов.
# База данных внешняя, а любые wipe/reseed-флаги принудительно отключены ниже.

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly ENV_FILE="${SCRIPT_DIR}/.env"
readonly COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
readonly PROJECT_NAME="billing_control"

die() {
  printf 'ОШИБКА: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local exit_code=$?
  printf 'ОШИБКА: hard_start.sh остановлен на строке %s (код %s).\n' "${BASH_LINENO[0]}" "${exit_code}" >&2
  exit "${exit_code}"
}
trap on_error ERR

read_env_value() {
  local key="$1"
  local value first last

  if ! value="$(
    awk -v wanted="${key}" '
      /^[[:space:]]*#/ { next }
      {
        separator = index($0, "=")
        if (separator == 0) { next }

        name = substr($0, 1, separator - 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
        if (name != wanted) { next }

        value = substr($0, separator + 1)
        sub(/\r$/, "", value)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        found += 1
        result = value
      }
      END {
        if (found != 1) { exit 2 }
        print result
      }
    ' "${ENV_FILE}"
  )"; then
    die "в ${ENV_FILE} параметр ${key} должен быть указан ровно один раз"
  fi

  if (( ${#value} >= 2 )); then
    first="${value:0:1}"
    last="${value: -1}"
    if [[ ( "${first}" == '"' && "${last}" == '"' ) || ( "${first}" == "'" && "${last}" == "'" ) ]]; then
      value="${value:1:${#value}-2}"
    fi
  fi

  printf '%s' "${value}"
}

command -v docker >/dev/null 2>&1 || die "Docker не установлен или недоступен в PATH"
[[ -f "${ENV_FILE}" ]] || die "не найден ${ENV_FILE}"
[[ -f "${COMPOSE_FILE}" ]] || die "не найден ${COMPOSE_FILE}"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 недоступен"

for flag in SEED_ON_STARTUP FORCE_RESEED WIPE_DB; do
  value="$(read_env_value "${flag}")"
  [[ "${value}" == "false" ]] || die "${flag} должен быть строго false; получено: ${value:-<пусто>}"
done

# Пул БД проверяем ДО остановки работающего стека: при DB_POOL_SIZE + DB_MAX_OVERFLOW >
# DB_CONNECTION_BUDGET backend не стартует, и сервис остался бы лежать.
pool_size="$(read_env_value DB_POOL_SIZE)"
pool_overflow="$(read_env_value DB_MAX_OVERFLOW)"
pool_budget="$(read_env_value DB_CONNECTION_BUDGET)"
for pair in "DB_POOL_SIZE:${pool_size}" "DB_MAX_OVERFLOW:${pool_overflow}" "DB_CONNECTION_BUDGET:${pool_budget}"; do
  [[ "${pair#*:}" =~ ^[0-9]+$ ]] || die "${pair%%:*} должен быть целым числом; получено: ${pair#*:}"
done
if (( pool_size + pool_overflow > pool_budget )); then
  die "DB_POOL_SIZE (${pool_size}) + DB_MAX_OVERFLOW (${pool_overflow}) > DB_CONNECTION_BUDGET (${pool_budget}) — backend не запустится. Исправьте .env (например 5/0/5)."
fi
printf 'Пул БД: %s соединений (overflow %s, бюджет %s).\n' "${pool_size}" "${pool_overflow}" "${pool_budget}"

# Переменные оболочки имеют приоритет над .env в Docker Compose. Поэтому не только
# проверяем файл, но и принудительно задаём безопасные значения для этого запуска.
export SEED_ON_STARTUP=false
export FORCE_RESEED=false
export WIPE_DB=false

compose=(
  docker compose
  --project-name "${PROJECT_NAME}"
  --project-directory "${SCRIPT_DIR}"
  --env-file "${ENV_FILE}"
  -f "${COMPOSE_FILE}"
)

printf 'Проверка production-конфигурации...\n'
"${compose[@]}" config --quiet

printf 'Сборка backend и frontend без остановки работающих контейнеров...\n'
"${compose[@]}" build backend frontend

printf 'Перезапуск только контейнеров проекта %s (без удаления volumes)...\n' "${PROJECT_NAME}"
"${compose[@]}" down --remove-orphans --timeout 30
"${compose[@]}" up -d --force-recreate --remove-orphans

printf 'Состояние сервисов:\n'
"${compose[@]}" ps

printf 'Последние логи backend и frontend:\n'
"${compose[@]}" logs --tail=100 backend frontend

printf 'Готово. Volumes, данные БД, образы и контейнеры других проектов не удалялись.\n'
