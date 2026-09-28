FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app
EXPOSE 8000
# Один процесс (без --workers): лимит соединений с БД = DB_POOL_SIZE, кеш авторизации точный.
# --timeout-graceful-shutdown меньше stop_grace_period (30 с): пул БД успевает закрыться штатно.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info", "--timeout-graceful-shutdown", "20"]
