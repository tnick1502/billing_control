# Billing Control — MRP / BOM Orders

Система управления производственными заказами: приборы, спецификации (BOM), месячные планы закупок, счета-фактуры, статистика.

## Содержание

- [Стек](#стек)
- [Архитектура](#архитектура)
- [Быстрый старт (dev)](#быстрый-старт-dev)
- [Деплой (prod)](#деплой-prod)
- [Переменные окружения](#переменные-окружения)
- [Структура проекта](#структура-проекта)
- [Функциональность](#функциональность)

---

## Стек

| Слой | Технология |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg |
| Frontend | SvelteKit 2, Svelte 4, Tailwind CSS 3, Chart.js 4 |
| База данных | PostgreSQL 16 |
| Контейнеры | Docker, Docker Compose |

---

## Архитектура

```
┌─────────────────┐        /api/*         ┌─────────────────┐
│   SvelteKit     │ ──────────────────▶  │   FastAPI       │
│   (Node, :3000) │   SSR proxy          │   (:8000)       │
└─────────────────┘                       └────────┬────────┘
                                                   │ asyncpg
                                          ┌────────▼────────┐
                                          │  PostgreSQL 16   │
                                          │   (:5432)        │
                                          └──────────────────┘
```

Фронтенд работает на Node (SvelteKit adapter-node). Все запросы `/api/*` проксируются через `hooks.server.ts` напрямую в бэкенд — CORS нужен только в dev-режиме.

Файлы счетов хранятся **в PostgreSQL** (таблица `file_contents`, bytea) — отдельный S3/объектный хостинг не требуется.

---

## Быстрый старт (dev)

### Вариант 1 — Docker Compose (рекомендуется)

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

| Сервис | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 (postgres/postgres) |

При первом запуске база заполняется тестовыми данными из `backend/app/tools/import_strick.json`.

### Вариант 2 — без Docker

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# убедиться что PostgreSQL запущен, потом:
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### Учётные данные по умолчанию

| Логин | Пароль | Роль |
|---|---|---|
| `admin` | `admin` | Администратор (полный доступ) |
| `employee` | `employee` | Сотрудник (просмотр + работа со счетами) |

---

## Деплой (prod)

`docker-compose.yml` (без postgres — БД должна быть внешней):

```bash
cp .env.example .env
# Заполнить: DATABASE_URL, PUBLIC_ORIGIN, CORS_ORIGINS
docker compose up --build -d
```

- Frontend — порт **80** (маппинг 80→3000)
- Backend — порт **8000**

### Минимальный .env для prod

```env
PUBLIC_ORIGIN=https://billing.example.com
CORS_ORIGINS=https://billing.example.com
DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/billing
DATABASE_SSL=true
DATABASE_SSL_VERIFY=false
SEED_ON_STARTUP=false
FORCE_RESEED=false
```

### Обновление

```bash
git pull
docker compose up --build -d
```

Схема БД обновляется автоматически через `schema_ensure.py` — Alembic не используется.

---

## Переменные окружения

### Backend

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders` | URL PostgreSQL |
| `DATABASE_SSL` | `false` | Включить SSL |
| `DATABASE_SSL_VERIFY` | `true` | Проверять сертификат |
| `PUBLIC_ORIGIN` | `http://localhost` | Публичный URL приложения |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Разрешённые CORS-источники (через запятую) |
| `SEED_ON_STARTUP` | `true` | Заполнить БД тестовыми данными при старте |
| `FORCE_RESEED` | `false` | Принудительно пересоздать тестовые данные |
| `WIPE_DB` | `false` | Полный сброс схемы при старте (только dev) |

### Frontend (docker-compose env)

| Переменная | Описание |
|---|---|
| `ORIGIN` | Публичный URL фронтенда (для SvelteKit CSRF) |
| `BACKEND_ORIGIN` | URL бэкенда внутри Docker-сети |
| `BODY_SIZE_LIMIT` | Максимальный размер тела запроса в байтах |

---

## Структура проекта

```
billing_control/
├── docker-compose.yml          # prod: backend + frontend (внешняя БД)
├── docker-compose.dev.yml      # dev: postgres + backend + frontend
├── .env.example                # Шаблон переменных окружения
├── backend/                    # FastAPI приложение
│   └── README.md               # Техническая документация бэкенда
└── frontend/                   # SvelteKit приложение
    └── README.md               # Документация фронтенда
```

---

## Функциональность

| Раздел | Описание |
|---|---|
| **Приборы** | Справочник изделий с псевдонимами и архивацией |
| **Детали** | Справочник компонентов, группировка по типу |
| **BOM** | Версионированные спецификации с поддержкой вложенных подприборов |
| **Заказы** | Производственные заказы с позициями приборов и прямыми позициями деталей |
| **Месячные планы** | Автоматический расчёт суммарной потребности деталей по заказам месяца с рекурсивным раскрытием BOM и выгрузкой в Excel по группам, шифрам, счетам и поставкам |
| **Счета** | Привязка счетов-фактур к позициям планов, отслеживание покрытия и поставки, хранение файлов |
| **Перенос остатков** | FIFO-перенос излишков по счетам между месяцами |
| **Статистика** | Графики заказов приборов и деталей в разрезе календарных месяцев |
| **Импорт** | Массовая загрузка приборов + BOM из подготовленного JSON |
| **Администрирование** | Управление пользователями (роли admin/employee) |
