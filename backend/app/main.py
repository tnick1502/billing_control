import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth import auth_middleware, ensure_default_users
from app.config import settings
from app.api import auth, bom, devices, files, imports, invoices, monthly_plans, orders, parts, stats
from app.database import Base, async_session_maker, engine, wipe_application_schema
from app.schema_ensure import ensure_schema
from app.seeds.init_data import seed_database


def _cors_allow_origins() -> list[str]:
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    extra = (settings.public_origin or "").strip().rstrip("/")
    if extra and extra not in origins:
        origins.append(extra)
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        f"[billing_control] DB TLS: ssl={settings.database_ssl} verify={settings.database_ssl_verify}",
        flush=True,
    )
    if settings.wipe_db:
        await wipe_application_schema(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await ensure_schema()

    # Устаревший блок с TRUNCATE — оставлен для справки; предпочтительнее wipe_application_schema выше.
    # async with async_session_maker() as session:
    #     from app.seeds.init_data import clear_database
    #     await clear_database(session)
    #     await session.commit()

    # Seed if enabled
    if settings.seed_on_startup:
        async with async_session_maker() as session:
            try:
                seeded = await seed_database(session, force=settings.force_reseed)
                await session.commit()
                if seeded:
                    print("Database seeded with test data")
            except Exception as e:
                await session.rollback()
                print(f"Seed warning: {e}")

    await ensure_default_users()

    yield

    await engine.dispose()


app = FastAPI(
    title="MRP BOM Orders API",
    description="API for managing orders, devices, BOMs, monthly plans and invoices",
    version="0.1.0",
    lifespan=lifespan,
)

# Чтобы в Docker/uvicorn в логах были traceback при 500 (logging.basicConfig до регистрации роутов)
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
    force=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.middleware("http")(auth_middleware)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    msg = str(exc.orig) if exc.orig else str(exc)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return JSONResponse(status_code=409, content={"detail": "Запись с такими данными уже существует"})
    if "foreign key" in msg.lower() or "violates" in msg.lower():
        return JSONResponse(status_code=400, content={"detail": "Некорректная ссылка (план, деталь и т.д.)"})
    # Не раскрываем клиенту внутренние детали БД — логируем на сервере, отдаём обобщённое сообщение.
    logging.getLogger(__name__).warning("IntegrityError (%s %s): %s", request.method, request.url.path, msg)
    return JSONResponse(status_code=400, content={"detail": "Не удалось сохранить данные: нарушение целостности"})



app.include_router(devices.router)
app.include_router(auth.router)
app.include_router(parts.router)
app.include_router(orders.router)
app.include_router(bom.router)
app.include_router(monthly_plans.router)
app.include_router(invoices.router)
app.include_router(files.router)
app.include_router(imports.router)
app.include_router(stats.router)


async def _check_db() -> None:
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))


@app.get("/health")
async def health():
    """Liveness + проверка доступности БД. Жёсткий таймаут, чтобы healthcheck не висел при недоступной БД."""
    try:
        await asyncio.wait_for(_check_db(), timeout=3)
    except Exception:
        logging.getLogger(__name__).warning("health: БД недоступна или не отвечает за 3с")
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "down"})
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
