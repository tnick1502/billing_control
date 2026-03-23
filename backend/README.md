# Backend (FastAPI)

См. [корневой README](../README.md) — запуск и переменные окружения.

```bash
poetry install
poetry run uvicorn app.main:app --reload
```

Таблицы в PostgreSQL создаются при старте приложения (SQLAlchemy `create_all`).
