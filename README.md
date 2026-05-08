# Billing control (MRP BOM Orders)

Веб-приложение для учёта заказов, приборов, спецификаций (BOM), месячных планов и счетов с загрузкой файлов в S3 (MinIO).

## Стек

- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL, MinIO (S3-совместимое хранилище)
- **Frontend**: SvelteKit, Tailwind CSS
- **Инфраструктура**: Docker Compose, Poetry (Python), npm (Node)

## Запуски

### Обычный запуск

Обычный запуск поднимает только **backend** и **frontend**. PostgreSQL и S3/MinIO берутся из `.env`.

```bash
./hard_start.sh
```

или:

```bash
docker compose up --build -d
```

### Dev запуск

Dev запуск поднимает локальные контейнеры **PostgreSQL**, **MinIO**, **backend** и **frontend**:

```bash
./hard_start_dev.sh
```

или:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

### URL после dev запуска

| Сервис | Адрес (локально) |
|--------|------------------|
| Приложение (UI) | http://localhost:3000/ |
| OpenAPI / Swagger | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001/ |
| S3 API | http://localhost:9000/ |

В обычном запуске frontend публикуется на `http://localhost/`, backend на `http://localhost:8000/`.

MinIO в dev: логин и пароль — `MINIO_ROOT_USER` и `MINIO_ROOT_PASSWORD` из окружения или `minioadmin` / `minioadmin`.

### Переменные окружения (`.env`)

Compose подхватывает файл **`.env`** в корне репозитория. Шаблон — **`.env.example`**.

Синтаксис `.env` для Docker Compose: только строки **`ИМЯ=значение`** и комментарии, где **первый символ строки — `#`**. Строка вроде заголовка без `#` и без `=` приведёт к ошибке `unexpected character in variable name`.

На сервере или при доступе не с `localhost` задайте, как минимум:

- **`PUBLIC_ORIGIN`** — публичный URL frontend без слэша в конце, например `http://203.0.113.10` или `https://example.com`.
- **`DATABASE_URL`** — PostgreSQL URL для backend (в проекте используется драйвер **asyncpg**: `postgresql+asyncpg://...`).
- **`DATABASE_SSL`** — `true`, если облачный PostgreSQL требует TLS (иначе `false` или не задавайте).
- **`DATABASE_SSL_VERIFY`** — `false`, если при `DATABASE_SSL=true` возникает `SSLCertVerificationError` (self-signed у провайдера); соединение остаётся по TLS, но без проверки цепочки сертификатов.
- **`S3_ENDPOINT_URL`** — S3 endpoint, доступный backend.
- **`S3_PUBLIC_ENDPOINT_URL`** — S3 endpoint, доступный браузеру для presigned-ссылок.
- **`S3_ACCESS_KEY`** / **`S3_SECRET_KEY`** / **`S3_BUCKET`** / **`S3_REGION`** — параметры S3.
- **`CORS_ORIGINS`** — список через запятую: ваш UI и при необходимости `PUBLIC_ORIGIN`.

Иначе ссылки «Скачать» могут указывать на неверный хост.

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

Для локального backend без контейнера используйте `docker-compose.dev.yml` для PostgreSQL/MinIO и экспортируйте `DATABASE_URL` / `S3_ENDPOINT_URL` на localhost.

Схема БД поднимается при старте приложения. Изменения моделей при разработке обычно сопровождают ручным SQL или пересозданием БД.

## Скрипт `hard_start.sh`

`hard_start.sh` перезапускает обычный стек. `hard_start_dev.sh` перезапускает dev стек с локальными PostgreSQL и MinIO.

## API (кратко)

Frontend проксирует запросы **`/api/*`** во внутренний backend.

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
