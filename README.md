# MRP BOM Orders Service

Сервис управления заказами, приборами, спецификациями (BOM), месячными планами и счетами с привязкой к S3.

## Стек

- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL, MinIO (S3)
- **Frontend**: SvelteKit, Tailwind CSS
- **Инфраструктура**: Docker, Poetry

## Запуск через Docker

```bash
docker compose up --build
```

- Приложение: http://localhost (через nginx)
- Backend API: http://localhost:8000
- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)

При первом запуске автоматически:
- создаются таблицы в БД (если их ещё нет)
- создаётся bucket в MinIO
- заполняется БД тестовыми данными

## Локальная разработка

### Backend

```bash
cd backend
poetry install
# Запустить PostgreSQL и MinIO: docker compose up postgres minio -d
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders
export S3_ENDPOINT_URL=http://localhost:9000
poetry run uvicorn app.main:app --reload
```

Схема БД создаётся при старте приложения (`create_all`). Для изменения структуры таблиц правьте модели и пересоздайте БД или примените SQL вручную.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend на http://localhost:5173 проксирует `/api` на backend.

## API

- `GET /stats/orders-devices-timeseries?date_from=&date_to=` — ряды по датам заказа и приборам за период
- `GET /stats/orders-parts-timeseries?part_id=&date_from=&date_to=` — ряды по прямым заказам детали за период
- `GET /health` — проверка
- `GET/POST /devices` — приборы
- `GET/POST /parts` — детали
- `GET/POST /orders` — заказы
- `GET/POST /devices/{id}/bom` — BOM прибора
- `GET/POST /monthly-plans` — месячные планы
- `POST /monthly-plans/generate` — генерация плана по заказам
- `GET/POST /invoices` — счета
- `POST /invoices/{id}/upload` — загрузка файла счёта в S3
