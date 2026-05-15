# Billing control (MRP BOM Orders)

Веб-приложение для учёта заказов, приборов, спецификаций (BOM), месячных планов и счетов.

**Вложения к счетам** (документы небольшого размера) хранятся в той же **PostgreSQL**: метаданные в `files`, двоичное тело в `file_contents` (отдельная строка на файл). Подробная логика бэкенда описана в [`backend/README.md`](backend/README.md).

## Стек

- **Backend**: FastAPI, SQLAlchemy 2 (async), PostgreSQL, Pydantic v2  
- **Frontend**: SvelteKit, Tailwind CSS  
- **Запуск**: Docker Compose; локально — Poetry или `pip` по `requirements.txt`, на фронте — npm  

## Быстрый старт

### Продакшн-подобный compose (свой PostgreSQL из `.env`)

```bash
./hard_start.sh
```

или:

```bash
docker compose up --build -d
```

Поднимаются **backend** и **frontend**. База указывается переменными в **`.env`** (шаблон — **`.env.example`**).

### Разработка: Postgres + приложение в Docker

```bash
./hard_start_dev.sh
```

или:

```bash
docker compose -f docker-compose.dev.yml up --build -d
```

| Сервис | URL (dev) |
|--------|-----------|
| UI | http://localhost:3000/ |
| Swagger | http://localhost:8000/docs |

В compose без `-f dev.yml` UI обычно на `http://localhost/`, API на `http://localhost:8000/`.

## Переменные окружения

Файл **`.env`** в корне репозитория. Для Docker Compose допустимы только строки `КЛЮЧ=значение` и комментарии с `#` в начале строки — иначе ошибка парсера.

Минимум для работы не на localhost:

- **`PUBLIC_ORIGIN`** — URL фронтенда без завершающего `/`  
- **`DATABASE_URL`** — `postgresql+asyncpg://...`  
- **`DATABASE_SSL`** / **`DATABASE_SSL_VERIFY`** — при необходимости TLS к облачному Postgres  
- **`CORS_ORIGINS`** — разрешённые origin для браузера, через запятую (включая ваш UI и при необходимости `PUBLIC_ORIGIN`)  
- **`SEED_ON_STARTUP`**, **`FORCE_RESEED`** — тестовые данные при старте (см. бэкенд README)  

## Схема базы и обновления без Alembic

При старте приложение вызывает `Base.metadata.create_all` и затем дополняет схему скриптом [`backend/app/schema_ensure.py`](backend/app/schema_ensure.py) (недостающие колонки, приведение таблиц `files` / `file_contents` к актуальной модели). Если база сильно устарела относительно кода, надёжнее пересоздать БД или перенести данные вручную.

## Локальная разработка фронта

```bash
cd frontend
npm install
npm run dev
```

Сервер: http://localhost:5173. Запросы `/api/*` проксируются на backend (см. `vite.config.ts`).

Backend без Docker: поднимите PostgreSQL, задайте `DATABASE_URL`, из каталога `backend`: `poetry run uvicorn app.main:app --reload`.

## PostgreSQL 15+: нет прав на `public`

Если при старте видите `permission denied for schema public`, под администратором БД выдайте роли из `DATABASE_URL` права `USAGE, CREATE` на схему `public` (или сделайте пользователя владельцем базы) и перезапустите backend.

## API (кратко)

Полная схема — **/docs** на API.

- `GET /health`  
- CRUD приборов, деталей, заказов, BOM, месячных планов  
- `POST monthly-plans/generate` — генерация плана из заказов  
- `POST /invoices` — создание счёта (**multipart**, обязательное поле файла)  
- `GET /files/{id}/download` — скачивание вложения  
- Статистика: `GET /stats/...`  

Скрипты **`hard_start.sh`** / **`hard_start_dev.sh`** перезапускают соответствующий стек Docker.
