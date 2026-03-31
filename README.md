# Billing control (MRP BOM Orders)

Веб-приложение для учёта заказов, приборов, спецификаций (BOM), месячных планов и счетов с загрузкой файлов в S3 (MinIO).

## Стек

- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL, MinIO (S3-совместимое хранилище)
- **Frontend**: SvelteKit, Tailwind CSS
- **Инфраструктура**: Docker Compose, nginx (обратный прокси), Poetry (Python), npm (Node)

## Запуск через Docker Compose

Из корня репозитория (перед первым запуском создайте файл пароля Portainer из `.env`):

```bash
python3 scripts/sync-portainer-password-from-env.py
docker compose up --build -d
```

Снаружи публикуются только **80** (nginx) и **5432** (PostgreSQL). Порт **8000** бэкенда на хост не открывается — API доступен только через nginx.

### URL после запуска

| Сервис | Адрес (локально) |
|--------|------------------|
| Приложение (UI) | http://localhost/ |
| OpenAPI / Swagger | http://localhost/api/docs |
| MinIO Console | http://localhost/minio/ |
| S3 API (для presigned-ссылок из браузера) | http://localhost/minio-s3/ |
| Portainer | http://localhost/portainer/ |

MinIO: логин и пароль — **`MINIO_ROOT_USER`** и **`MINIO_ROOT_PASSWORD`** в `.env` (в примере — `minioadmin` / `minioadmin`).

Portainer: логин **`admin`**, пароль — из **`PORTAINER_ADMIN_PASSWORD`** в `.env`, перед запуском compose создайте файл: `python3 scripts/sync-portainer-password-from-env.py` (образ Portainer без shell, пароль передаётся только через файл `portainer_admin_password`). Только при первом создании данных Portainer.

### Переменные окружения (`.env`)

Compose подхватывает файл **`.env`** в корне репозитория. Шаблон — **`.env.example`**.

На сервере или при доступе не с `localhost` задайте, как минимум:

- **`PUBLIC_ORIGIN`** — публичный URL без слэша в конце, например `http://203.0.113.10` или `https://example.com`. Нужен для MinIO, presigned URL и автоматически добавляется в CORS бэкенда. Фронт за nginx берёт origin из заголовков `X-Forwarded-*`, поэтому по IP/домену приложение работает без жёсткого `ORIGIN=http://localhost` в контейнере.
- **`S3_PUBLIC_ENDPOINT_URL`** — тот же хост + путь к S3 за nginx, например `http://203.0.113.10/minio-s3`.
- **`CORS_ORIGINS`** — список через запятую: ваш UI и при необходимости `PUBLIC_ORIGIN`.
- **`MINIO_ROOT_USER`** / **`MINIO_ROOT_PASSWORD`** — MinIO и ключи S3 для бэкенда.
- **`PORTAINER_ADMIN_PASSWORD`** — пароль админа Portainer; перед `docker compose up` выполните `python3 scripts/sync-portainer-password-from-env.py` (см. таблицу URL).

Иначе ссылки «Скачать» и консоль MinIO могут указывать на неверный хост.

### Первый запуск

При старте бэкенда (если включён сид):

- создаются таблицы в БД (при отсутствии);
- создаётся bucket в MinIO;
- при необходимости заполняется БД тестовыми данными.

## Локальная разработка

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev-сервер: http://localhost:5173. В `vite.config.ts` запросы **`/api/*`** проксируются на **`http://localhost:8000`** (префикс `/api` снимается).

### Backend

```bash
cd backend
poetry install
```

Нужен работающий **PostgreSQL**. Из корня репозитория:

```bash
docker compose up postgres -d
```

**MinIO:** в текущем `docker-compose.yml` порты MinIO на хост **не проброшены** — доступ к API и консоли идёт через nginx на порту 80. Для локального **uvicorn** на машине удобно поднять MinIO отдельно с публикацией портов, например:

```bash
docker run -d --name minio-dev -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

Далее:

```bash
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders
export S3_ENDPOINT_URL=http://localhost:9000
export S3_PUBLIC_ENDPOINT_URL=http://localhost:9000
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Схема БД поднимается при старте приложения. Изменения моделей при разработке обычно сопровождают ручным SQL или пересозданием БД.

## Скрипт `hard_start.sh`

Агрессивно очищает локальный Docker (контейнеры, образы, prune), делает `git pull` и поднимает стек. Используйте только если осознаёте последствия для **всех** образов/контейнеров на машине.

## API (кратко)

Базовый префикс за nginx: **`/api/`** (внутри контейнера бэкенд слушает корень).

- `GET /health` — проверка
- `GET/POST /devices` — приборы
- `GET/POST /parts` — детали
- `GET/POST /orders` — заказы
- `GET/POST /devices/{id}/bom` — BOM прибора
- `GET/POST /monthly-plans` — месячные планы
- `POST /monthly-plans/generate` — генерация плана по заказам
- `GET/POST /invoices` — счета
- `POST /invoices/{id}/upload` — загрузка файла счёта в S3
- `GET /stats/orders-devices-timeseries?date_from=&date_to=` — ряды по заказам и приборам
- `GET /stats/orders-parts-timeseries?part_id=&date_from=&date_to=` — ряды по заказам детали

Полная схема — в **http://localhost/api/docs** после запуска compose.
