# Frontend — техническая документация

SvelteKit-приложение. Точка входа: `src/routes/+layout.svelte`.

## Содержание

- [Стек](#стек)
- [Структура проекта](#структура-проекта)
- [Запуск](#запуск)
- [Роутинг и страницы](#роутинг-и-страницы)
- [API-клиент](#api-клиент)
- [Прокси к бэкенду](#прокси-к-бэкенду)
- [Аутентификация](#аутентификация)
- [Утилиты форматирования](#утилиты-форматирования)
- [Сборка и деплой](#сборка-и-деплой)
- [Переменные окружения](#переменные-окружения)

---

## Стек

```
SvelteKit 2 + Svelte 4      — фреймворк, SSR, роутинг
Tailwind CSS 3              — утилитарный CSS
Chart.js 4                  — графики (динамический import)
TypeScript 5                — типизация
Vite 5                      — сборщик
@sveltejs/adapter-node      — запуск в Node.js (production build)
```

---

## Структура проекта

```
frontend/
├── src/
│   ├── app.html             # HTML-шаблон (точка монтирования SvelteKit)
│   ├── app.css              # Глобальные стили + Tailwind directives
│   ├── hooks.server.ts      # SSR-хук: проксирование /api/* → backend
│   │
│   ├── lib/
│   │   ├── api.ts           # Все типы и функции для обращения к API
│   │   └── format.ts        # Утилиты форматирования (числа, даты, размер файла)
│   │
│   └── routes/
│       ├── +layout.svelte   # Навигация, проверка авторизации, logout
│       ├── +page.ts         # Редирект с / на /monthly-plans
│       ├── login/           # Страница входа
│       ├── devices/         # Приборы (CRUD + поиск + BOM)
│       ├── parts/           # Детали (CRUD + группировка по типу)
│       ├── bom/             # Спецификации (просмотр BOM дерева)
│       ├── orders/          # Заказы (CRUD + позиции)
│       ├── monthly-plans/   # Месячные планы (навигатор, группы деталей)
│       ├── invoices/        # Счета (CRUD + привязки + файлы)
│       ├── statistics/      # Графики заказов
│       ├── import/          # Загрузка JSON импорта
│       └── admin/           # Управление пользователями
│
├── static/
│   └── favicon.svg
│
├── Dockerfile               # Multistage: builder (npm run build) → node:20-alpine
├── package.json
├── svelte.config.js
├── vite.config.ts
├── tailwind.config.js
└── postcss.config.js
```

---

## Запуск

### Dev

```bash
npm install
npm run dev        # http://localhost:5173
```

Hot-reload работает из коробки. Backend должен быть доступен на `http://localhost:8000`.

### Проверка типов

```bash
npx svelte-check --tsconfig ./tsconfig.json
```

### Production build

```bash
npm run build      # собирает в build/
node build         # запускает сервер на :3000
```

---

## Роутинг и страницы

Файловый роутинг SvelteKit: каждая директория в `src/routes/` соответствует пути.

| Путь | Файл | Назначение |
|---|---|---|
| `/` | `+page.ts` | Redirect → `/monthly-plans` |
| `/login` | `login/+page.svelte` | Форма входа |
| `/devices` | `devices/+page.svelte` | Справочник приборов + псевдонимы + BOM-версии |
| `/parts` | `parts/+page.svelte` | Справочник деталей, сгруппированных по типу |
| `/bom` | `bom/+page.svelte` | Просмотр и редактирование спецификаций |
| `/orders` | `orders/+page.svelte` | Производственные заказы с позициями |
| `/monthly-plans` | `monthly-plans/+page.svelte` | Месячные планы с навигатором и группами деталей |
| `/invoices` | `invoices/+page.svelte` | Счета-фактуры с привязками к планам |
| `/statistics` | `statistics/+page.svelte` | Графики заказов по месяцам |
| `/import` | `import/+page.svelte` | Загрузка bulk-импорта JSON |
| `/admin` | `admin/+page.svelte` | Управление пользователями |

### Навигация и авторизация

`+layout.svelte` при монтировании:
1. Проверяет наличие токена в `localStorage`.
2. Вызывает `GET /api/auth/me` (timeout 15с).
3. При успехе — показывает навигацию и текущий раздел.
4. При ошибке / нет токена — redirect на `/login`.
5. На странице `/login` при наличии валидного токена — redirect на `/monthly-plans`.

---

## API-клиент

Файл: `src/lib/api.ts`.

Все обращения к бэкенду — через объект `api`:

```typescript
import { api } from '$lib/api';

// Примеры:
const devices = await api.devices.list();
const plan = await api.monthlyPlans.generate({ month: '2026-03-01', replace: true });
const payload = await api.stats.ordersPartsMonthlyTimeseries('2026-01-01', '2026-12-31');
```

**Структура `api`:**

```
api.auth          — login, logout, me, users CRUD
api.devices       — list, get, create, update, delete, archive, aliases, bomVersions
api.parts         — list, get, create, update, archive, delete
api.orders        — list, get, create, update, delete, items
api.bom           — versions (CRUD), items (CRUD)
api.monthlyPlans  — list, generate, devices, partsWithCoverage,
                    updatePlanPartDelivered, partFiles, remainders
api.invoices      — list, get, create, update, delete,
                    files (list, upload, download, delete),
                    parts (create, update, delete)
api.files         — downloadBlob
api.stats         — ordersDevicesTimeseries, ordersPartsMonthlyTimeseries, ordersPartsTimeseries
```

**Базовый URL:** `/api` — проксируется через SvelteKit server hook.

**Аутентификация:** `Authorization: Bearer <token>` из `localStorage` (`billing_control_token`).

**Вспомогательные функции:**

```typescript
getAuthToken()    // читает токен из localStorage
setAuthToken(t)   // сохраняет токен
clearAuthToken()  // удаляет токен
```

**Обработка ошибок:** все fetch-запросы оборачиваются в проверку `response.ok`, при ошибке бросают `Error` с сообщением из `detail` тела ответа.

---

## Прокси к бэкенду

Файл: `src/hooks.server.ts`.

SSR-хук перехватывает все запросы на `/api/*` и проксирует их в `BACKEND_ORIGIN`:

```
/api/devices  →  http://backend:8000/devices
/api/auth/me  →  http://backend:8000/auth/me
```

GET/HEAD — стримятся напрямую. POST/PUT/PATCH/DELETE — тело буферизуется через `arrayBuffer()` (нужно для multipart-загрузок файлов).

В dev-режиме (`npm run dev`) Vite-прокси перенаправляет `/api/*` на `http://localhost:8000` через `vite.config.ts`.

---

## Аутентификация

Токен хранится в `localStorage` под ключом `billing_control_token`. Передаётся в каждом запросе через заголовок `Authorization: Bearer`.

После логина токен сохраняется, при logout — удаляется + вызывается `POST /api/auth/logout`.

---

## Утилиты форматирования

Файл: `src/lib/format.ts`.

```typescript
formatQty(v)          // число с 3 знаками: "10.500"
formatIntegerQty(v)   // целое: "10"
formatAmount(v)       // деньги: "18 000.50"
formatDate(v)         // дата: "15.03.2026" или "—"
formatDateTime(v)     // дата+время: "15.03.2026 14:32"
formatFileSize(bytes) // "1.2 МБ", "340 КБ"
```

---

## Сборка и деплой

### Docker (multistage)

```dockerfile
FROM node:20-alpine AS builder
# npm install + npm run build → build/

FROM node:20-alpine
# копирует build/ + node_modules + package.json
CMD ["node", "build"]
```

Сервер слушает на `0.0.0.0:3000`.

### Переменные окружения (runtime, Node)

| Переменная | Описание |
|---|---|
| `ORIGIN` | Публичный URL приложения (для SvelteKit CSRF защиты) |
| `BACKEND_ORIGIN` | URL бэкенда для серверного прокси (default: `http://backend:8000`) |
| `PROTOCOL_HEADER` | Заголовок для определения протокола за reverse proxy (`x-forwarded-proto`) |
| `HOST_HEADER` | Заголовок для определения хоста (`x-forwarded-host`) |
| `BODY_SIZE_LIMIT` | Максимальный размер тела запроса в байтах (default: 512KB, для файлов нужно увеличить) |

---

## Переменные окружения

В dev-режиме переменные для Vite задаются в `.env` в корне `frontend/` (не нужны при работе через docker-compose.dev.yml).

```env
# frontend/.env (только для локального dev без Docker)
VITE_API_BASE=/api
```

Остальные настройки бэкенда задаются в корневом `.env`.
