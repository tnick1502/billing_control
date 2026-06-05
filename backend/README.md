# Backend — техническая документация

FastAPI-приложение в пакете `app/`. Точка входа: `app/main.py`.

## Содержание

- [Стек и зависимости](#стек-и-зависимости)
- [Структура пакета](#структура-пакета)
- [Запуск](#запуск)
- [Конфигурация](#конфигурация)
- [База данных](#база-данных)
- [Модели данных](#модели-данных)
- [Схема БД (ER)](#схема-бд-er)
- [API роутеры](#api-роутеры)
- [Сервисный слой](#сервисный-слой)
- [Аутентификация и авторизация](#аутентификация-и-авторизация)
- [Жизненный цикл приложения](#жизненный-цикл-приложения)
- [Seed-данные](#seed-данные)
- [Инструмент массового импорта](#инструмент-массового-импорта)
- [Миграции схемы](#миграции-схемы)
- [Хранение файлов](#хранение-файлов)
- [Обработка ошибок](#обработка-ошибок)

---

## Стек и зависимости

```
Python 3.12
├── FastAPI 0.115          — веб-фреймворк, автодокументация Swagger/ReDoc
├── SQLAlchemy 2 (async)   — ORM, декларативные модели, async-сессии
├── asyncpg 0.30           — асинхронный драйвер PostgreSQL
├── Pydantic v2            — валидация данных, схемы запроса/ответа
├── pydantic-settings      — конфигурация из переменных окружения / .env
├── bcrypt                 — хэширование паролей
├── python-multipart       — загрузка файлов (multipart/form-data)
└── uvicorn[standard]      — ASGI-сервер
```

Зависимости описаны в `pyproject.toml` (Poetry) и продублированы в `requirements.txt` для Docker.

---

## Структура пакета

```
backend/
├── app/
│   ├── main.py              # Точка входа: FastAPI app, lifespan, middleware, роутеры
│   ├── config.py            # Настройки через pydantic-settings (читает .env)
│   ├── database.py          # SQLAlchemy engine, session maker, Base, wipe_application_schema
│   ├── auth.py              # Middleware, хэширование паролей, ensure_default_users
│   ├── schema_ensure.py     # Безмигрейшн обновление схемы (ALTER TABLE IF NOT EXISTS)
│   │
│   ├── models/              # SQLAlchemy ORM модели
│   │   ├── __init__.py      # Реэкспорт всех моделей (обязательно импортировать перед create_all)
│   │   ├── device.py        # Device, DeviceAlias
│   │   ├── part.py          # Part
│   │   ├── order.py         # Order, OrderItem
│   │   ├── order_part_item.py  # OrderPartItem (прямые позиции деталей в заказе)
│   │   ├── bom.py           # DeviceBomVersion, DeviceBomItem
│   │   ├── monthly_plan.py  # MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart, MonthlyPlanPartFile
│   │   ├── invoice.py       # Invoice, File, FileContent, InvoiceFile, InvoicePartLink
│   │   └── auth.py          # User, AuditLog
│   │
│   ├── api/                 # FastAPI роутеры (один файл = один домен)
│   │   ├── __init__.py
│   │   ├── auth.py          # POST /auth/login, /logout, GET /auth/me, /auth/users
│   │   ├── devices.py       # CRUD /devices
│   │   ├── parts.py         # CRUD /parts
│   │   ├── orders.py        # CRUD /orders
│   │   ├── bom.py           # CRUD /bom/devices/{id}/versions, /bom/versions/{id}/items
│   │   ├── monthly_plans.py # /monthly-plans: генерация, детали, файлы поставки, остатки
│   │   ├── invoices.py      # CRUD /invoices, /invoices/{id}/parts (привязки к планам)
│   │   ├── files.py         # GET /files/{id}/download
│   │   ├── imports.py       # POST /imports/bulk (загрузка JSON)
│   │   └── stats.py         # GET /stats/orders-devices-timeseries, /orders-parts-monthly-timeseries
│   │
│   ├── schemas/
│   │   └── common.py        # Pydantic-схемы запросов и ответов (все домены)
│   │
│   ├── services/
│   │   ├── monthly_plan.py  # generate_monthly_plan: рекурсивное раскрытие BOM
│   │   ├── carryover.py     # recompute_carryover_links: FIFO-перенос остатков
│   │   └── file_storage.py  # save_bytes_as_file: сохранение файла в БД
│   │
│   ├── seeds/
│   │   ├── init_data.py     # seed_database: тестовые данные при старте
│   │   └── fixtures/
│   │       └── sample_invoice_attachment.txt
│   │
│   └── tools/
│       ├── bulk_import.py   # CLI/API инструмент массового импорта из JSON
│       ├── import_strick.json   # Реальные данные приборов (используется при seed)
│       ├── import_example.json  # Пример формата для импорта
│       └── IMPORT_INSTRUCTION.md
│
├── Dockerfile
├── pyproject.toml
└── requirements.txt
```

---

## Запуск

### Локально (dev)

```bash
# из директории backend/
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Docker

```bash
# из корня проекта
docker compose -f docker-compose.dev.yml up --build -d
```

### Переменные окружения

Читаются из `.env` в рабочей директории или из окружения Docker:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders
SEED_ON_STARTUP=true
FORCE_RESEED=false
WIPE_DB=false
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
PUBLIC_ORIGIN=http://localhost
DATABASE_SSL=false
DATABASE_SSL_VERIFY=true
```

---

## Конфигурация

Файл: `app/config.py` → класс `Settings(BaseSettings)`.

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| `database_url` | str | `postgresql+asyncpg://...` | DSN подключения к PostgreSQL |
| `database_ssl` | bool | `false` | SSL для соединения с БД |
| `database_ssl_verify` | bool | `true` | Верификация SSL-сертификата |
| `cors_origins` | str | `http://localhost:5173,...` | Разрешённые CORS-источники |
| `public_origin` | str\|None | `None` | Публичный URL (добавляется в CORS) |
| `seed_on_startup` | bool | `true` | Засеять тестовые данные если БД пуста |
| `force_reseed` | bool | `false` | Сбросить и пересоздать тестовые данные |
| `wipe_db` | bool | `false` | Drop + create all таблиц при старте |

Все bool-поля парсятся устойчиво к строкам `"true"/"false"/"1"/"0"` через `coerce_env_bool_fields`.

---

## База данных

Файл: `app/database.py`.

```python
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
)

async_session_maker = async_sessionmaker(
    engine,
    expire_on_commit=False,   # объекты живы после commit
    autocommit=False,
    autoflush=False,
)
```

`get_db()` — FastAPI-dependency, открывает сессию, делает `commit` при успехе и `rollback` при исключении.

`wipe_application_schema(engine)` — полный drop + create_all, только для dev (`WIPE_DB=true`).

---

## Модели данных

### Device / DeviceAlias

```
devices
  id, primary_name, model, description, is_archived, created_at

device_aliases
  id, device_id FK→devices, alias_name [UNIQUE per device], created_at
```

Прибор может иметь несколько псевдонимов для поиска.

### Part

```
parts
  id, name, cipher, article, part_type, description, is_archived, created_at
```

`cipher` — конструкторский шифр детали. `part_type` — текстовая категория (Крепёж, Уплотнения, Электроника…).

### Order / OrderItem / OrderPartItem

```
orders
  id, order_date, customer, contract_no, description, created_at

order_items                              ← позиции приборов
  id, order_id FK→orders, device_id FK→devices,
  bom_version_id FK→device_bom_versions (nullable, SET NULL on delete),
  qty NUMERIC(18,3), price NUMERIC(18,2), note

order_part_items                         ← прямые позиции деталей (без прибора)
  id, order_id FK→orders, part_id FK→parts,
  qty NUMERIC(18,3), price NUMERIC(18,2), note
```

### DeviceBomVersion / DeviceBomItem

```
device_bom_versions
  id, device_id FK→devices, name, description,
  version INT [UNIQUE per device], status (draft|current|active|archived),
  valid_from, valid_to, created_at

device_bom_items                         ← позиция спецификации
  id, bom_version_id FK→device_bom_versions,
  part_id FK→parts (nullable),           ← деталь
  sub_device_id FK→devices (nullable),   ← подприбор
  sub_bom_version_id FK→device_bom_versions (nullable, SET NULL),
  qty_per_device INT, scrap_rate NUMERIC(10,6), note
```

**Инвариант:** ровно одно из `part_id` / `sub_device_id` должно быть заполнено (enforced в API). `item_type` — computed property: `"part"` или `"sub_device"`.

### MonthlyPlan / MonthlyPlanDevice / MonthlyPlanPart / MonthlyPlanPartFile

```
monthly_plans
  id, month DATE (первый день месяца), revision INT [UNIQUE per month],
  status, generated_at, generated_by, note

monthly_plan_devices                     ← итого приборов в плане
  id, plan_id, device_id, bom_version_id, qty_total NUMERIC(18,3)

monthly_plan_parts                       ← итого деталей в плане
  id, plan_id, part_id,
  qty_required NUMERIC(18,6),            ← потребность из BOM × кол-во приборов
  qty_final NUMERIC(18,6),               ← с учётом scrap_rate
  qty_delivered NUMERIC(18,6),           ← вручную, факт поставки
  delivery_complete BOOL (nullable),
  coverage_complete BOOL (nullable)

monthly_plan_part_files                  ← вложения (документы поставки)
  id, plan_part_id FK→monthly_plan_parts, file_id FK→files
```

### Invoice / InvoicePartLink / File / FileContent

```
invoices
  id, invoice_no, invoice_date, supplier, total_amount NUMERIC(18,2),
  payment_date DATE (nullable), description, note, created_at

invoice_part_links                       ← привязка счёта к детали в плане
  id, invoice_id FK→invoices, plan_id FK→monthly_plans,
  part_id FK→parts, qty_covered NUMERIC(18,6),
  is_carryover BOOL DEFAULT false        ← автоперенос остатка

files
  id, filename, content_type, size_bytes, uploaded_at

file_contents                            ← байты файла в БД
  file_id PK FK→files, data BYTEA

invoice_files                            ← связь счёт ↔ файл
  invoice_id, file_id, role, created_at  ← PK (invoice_id, file_id)
```

### User / AuditLog

```
users
  id, username [UNIQUE], password (bcrypt), full_name,
  role (admin|employee), is_active BOOL, session_token, created_at

audit_log
  id, user_id FK→users, action, entity_type, entity_id, created_at
```

---

## Схема БД (ER)

```
devices ──< device_aliases
devices ──< device_bom_versions ──< device_bom_items >── parts
                                         └──< device_bom_items >── devices (sub_device)

orders ──< order_items >── devices
       └──< order_part_items >── parts

monthly_plans ──< monthly_plan_devices >── devices
              └──< monthly_plan_parts  >── parts
                       └──< monthly_plan_part_files >── files >── file_contents

invoices ──< invoice_part_links >── monthly_plans
                                └── parts
         └──< invoice_files >── files
```

---

## API роутеры

Все роутеры подключены в `main.py`. Базовые пути:

| Роутер | Prefix | Основные эндпоинты |
|---|---|---|
| `auth.py` | `/auth` | `POST /login`, `POST /logout`, `GET /me`, `GET /users`, `POST /users`, `DELETE /users/{id}` |
| `devices.py` | `/devices` | CRUD + `GET /devices/{id}/bom-versions`, поиск |
| `parts.py` | `/parts` | CRUD + архивация |
| `orders.py` | `/orders` | CRUD + `GET /orders/{id}/items` |
| `bom.py` | `/bom` | `GET/POST /bom/devices/{id}/versions`, `GET/POST/DELETE /bom/versions/{id}/items` |
| `monthly_plans.py` | `/monthly-plans` | `POST /generate`, `GET /{id}/devices`, `GET /{id}/parts-with-coverage`, `PATCH /{plan_id}/parts/{part_id}/delivered`, `GET /remainders` |
| `invoices.py` | `/invoices` | CRUD + `POST /{id}/files`, `GET/POST/PATCH/DELETE /{id}/parts` |
| `files.py` | `/files` | `GET /{id}/download` |
| `imports.py` | `/imports` | `POST /imports/bulk` (JSON) |
| `stats.py` | `/stats` | `GET /orders-devices-timeseries`, `GET /orders-parts-monthly-timeseries`, `GET /orders-parts-timeseries` |

Документация автогенерируется: http://localhost:8000/docs (Swagger UI), http://localhost:8000/redoc.

---

## Сервисный слой

### `services/monthly_plan.py` — `generate_monthly_plan`

Генерирует (или пересоздаёт) месячный план:
1. Собирает все заказы за указанный месяц.
2. Для каждой позиции заказа (прибор + BOM) вызывает `_expand_bom` — **рекурсивное раскрытие** BOM с обнаружением циклов через `ancestor_device_ids`.
3. Прямые позиции деталей (`order_part_items`) суммируются напрямую.
4. Результат записывается в `monthly_plan_devices` и `monthly_plan_parts`.
5. Вызывает `recompute_carryover_links` для пересчёта переносов.

### `services/carryover.py` — `recompute_carryover_links`

FIFO-перенос излишков между месяцами:
1. По каждой детали собирает хронологию счетов (реальные привязки + потребность по планам).
2. Если в месяце N заказано больше чем нужно — излишек переносится в месяц N+1 как `InvoicePartLink` с `is_carryover=True`.
3. При любом изменении планов/привязок вся цепочка пересобирается с нуля (DELETE старых carryover-ссылок → INSERT новых).

### `services/file_storage.py` — `save_bytes_as_file`

Сохраняет bytes в PostgreSQL: создаёт запись `File` + `FileContent` в одной транзакции. Возвращает `File`.

---

## Аутентификация и авторизация

Файл: `app/auth.py`.

**Механизм:** Bearer-токен в заголовке `Authorization`. Токен (64-байт URL-safe) хранится в `users.session_token`.

**Middleware** `auth_middleware`:
- Публичные пути (`/health`, `/auth/login`, `/docs`, `/redoc`, `/openapi.json`, `/assets/*`) — без проверки.
- GET/HEAD/OPTIONS — разрешены для всех аутентифицированных.
- `employee` — только чтение + `/auth/logout` + всё на `/invoices/*` (создание, правка, загрузка файлов).
- `admin` — полный доступ ко всем методам и путям.

**Роли:**

| Роль | Права |
|---|---|
| `admin` | Все операции (CRUD приборов, деталей, BOM, заказов, планов, счетов, пользователей) |
| `employee` | GET везде + создание/правка/удаление счетов и их привязок |

`ensure_default_users()` вызывается при старте — создаёт `admin/admin` и `employee/employee` если таблица пуста.

Аудит записей хранится в `audit_log` (сейчас заполняется для операций с пользователями).

---

## Жизненный цикл приложения

`lifespan` в `main.py` выполняется при старте и остановке:

**Старт:**
1. Если `WIPE_DB=true` → `wipe_application_schema` (drop + create all).
2. `Base.metadata.create_all` — создание отсутствующих таблиц.
3. `ensure_schema()` — безмигрейшн патчинг схемы (ALTER TABLE IF NOT EXISTS).
4. Если `SEED_ON_STARTUP=true` → `seed_database(force=FORCE_RESEED)`.
5. `ensure_default_users()` — создание дефолтных пользователей.

**Остановка:**
- `engine.dispose()` — закрытие пула соединений.

---

## Seed-данные

Файл: `app/seeds/init_data.py` → `seed_database(session, force)`.

Если БД не пуста и `force=False` — пропускается.

**Процесс:**
1. Загружает `app/tools/import_strick.json` → вызывает `_bulk_import` (те же 20 приборов с BOM что и при ручном импорте).
2. Запрашивает из БД все загруженные приборы с активными BOM.
3. Создаёт именованные заказы (январь–март 2026) на первые 3 прибора, включая 1 составной.
4. Создаёт 120 объёмных заказов (март–апрель 2026), циклически по всем 20 приборам.
5. Генерирует месячные планы за март и апрель.
6. Создаёт 30 тестовых счетов с вложениями (`fixtures/sample_invoice_attachment.txt`).

---

## Инструмент массового импорта

Файл: `app/tools/bulk_import.py`.

**Формат JSON:**

```json
{
  "format": "billing_control.bulk_import",
  "version": 1,
  "devices": [
    {
      "primary_name": "Камера А-100",
      "model": "PG.08.00.00.000",
      "description": "...",
      "bom": {
        "name": "Спецификация v1",
        "version": 1,
        "status": "active",
        "items": [
          {
            "part": { "name": "Поршень", "cipher": "02.001", "part_type": "Изготавливаемые детали" },
            "qty_per_device": 1
          },
          {
            "sub_device": "Поршневой узел ЛИГА 100кН",
            "sub_bom_version": 1,
            "qty_per_device": 2
          }
        ]
      }
    }
  ]
}
```

**Алгоритм:**
1. Парсинг и валидация JSON (`parse_document`).
2. Фаза 1: создание/нахождение standalone-деталей.
3. Фаза 2: создание/нахождение всех приборов (чтобы ссылки на подприборы разрешались).
4. Фаза 3: создание BOM-версий и их позиций. Идемпотентно — повторный запуск не создаёт дублей.

**CLI-запуск:**

```bash
# из backend/
python -m app.tools.bulk_import path/to/file.json
python -m app.tools.bulk_import path/to/file.json --dry-run
python -m app.tools.bulk_import path/to/file.json --update-existing
```

**API:** `POST /imports/bulk` — тот же файл в multipart/form-data.

---

## Миграции схемы

Alembic **не используется**. Вместо него — `app/schema_ensure.py` → `ensure_schema()`.

Подход: каждый `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` идемпотентен. При добавлении нового поля в ORM-модель нужно добавить соответствующий ALTER в `_PG_STATEMENTS`.

Текущие патчи включают:
- Добавление колонок `description`, `cipher`, `article`, `is_archived` в различные таблицы.
- Удаление устаревших колонок (`is_active`, `uom`, `status`, `currency`).
- Миграция `invoice_files` на составной PK `(invoice_id, file_id)`.
- Миграция `file_contents` (bytea) вместо старого object-storage.
- `device_bom_items.part_id` сделан nullable для поддержки подприборов.
- Добавление `sub_device_id`, `sub_bom_version_id` в `device_bom_items`.

При деплое новой версии схема обновляется автоматически при старте контейнера.

---

## Хранение файлов

Файлы (вложения к счетам, документы поставки) хранятся **в PostgreSQL**:

```
files            — метаданные: filename, content_type, size_bytes, uploaded_at
file_contents    — байты: file_id PK → files, data BYTEA
```

Загрузка: `POST /invoices/{id}/files` или через `monthly-plans/{plan_id}/parts/{part_id}/files`.  
Скачивание: `GET /files/{id}/download` — стримит `data` из `file_contents` с заголовком `Content-Disposition: attachment`.

`services/file_storage.py::save_bytes_as_file(session, data, filename, content_type)` — утилита для сохранения в рамках транзакции.

---

## Обработка ошибок

В `main.py` зарегистрированы глобальные обработчики:

- `IntegrityError` → 409 (unique constraint) или 400 (foreign key) с читаемым сообщением.
- Прочие исключения — стандартный FastAPI 422/500.

Логирование: `logging.basicConfig(level=INFO)`. В Docker-контейнере трейсбеки 500 видны в `docker logs`.

`GET /health` — эндпоинт для healthcheck: всегда возвращает `{"status": "ok"}` без проверки БД.
