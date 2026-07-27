import asyncio
from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, TimeoutError as SQLAlchemyTimeoutError

from app.auth import auth_middleware, ensure_default_users
from app.config import settings
from app.api import auth, bom, devices, files, imports, invoices, monthly_plans, orders, parts, stats
from app.database import Base, async_session_maker, engine, pool_snapshot, wipe_application_schema
from app.schema_ensure import ensure_schema
from app.seeds.init_data import seed_database

log = logging.getLogger(__name__)


def _pool_status() -> str:
    try:
        snapshot = pool_snapshot()
        return " ".join(f"{key}={value}" for key, value in snapshot.items())
    except Exception:
        return "unavailable"


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _cors_allow_origins() -> list[str]:
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    extra = (settings.public_origin or "").strip().rstrip("/")
    if extra and extra not in origins:
        origins.append(extra)
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "startup db_ssl=%s db_ssl_verify=%s db_pool_size=%s db_max_overflow=%s "
        "db_connection_budget=%s db_pool_timeout=%ss db_pool_recycle=%ss log_requests=%s",
        settings.database_ssl,
        settings.database_ssl_verify,
        settings.db_pool_size,
        settings.db_max_overflow,
        settings.db_connection_budget,
        settings.db_pool_timeout,
        settings.db_pool_recycle,
        settings.log_requests,
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
    level=getattr(logging, settings.log_level),
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


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
    request.state.request_id = request_id
    started = perf_counter()
    try:
        response = await call_next(request)
    except (SQLAlchemyTimeoutError, DBAPIError):
        duration_ms = (perf_counter() - started) * 1000
        log.exception(
            "request_db_failed request_id=%s method=%s path=%s duration_ms=%.1f pool=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
            _pool_status(),
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "База данных временно недоступна. Повторите запрос через несколько секунд.",
                "request_id": request_id,
            },
            headers={"x-request-id": request_id, "retry-after": "2"},
        )
    except Exception:
        duration_ms = (perf_counter() - started) * 1000
        log.exception(
            "request_failed request_id=%s method=%s path=%s duration_ms=%.1f pool=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
            _pool_status(),
        )
        raise

    response.headers["x-request-id"] = request_id
    if settings.log_requests:
        user = getattr(request.state, "user", None)
        log.info(
            "request request_id=%s method=%s path=%s status=%s duration_ms=%.1f user=%s pool=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            (perf_counter() - started) * 1000,
            getattr(user, "username", "-"),
            _pool_status(),
        )
    return response


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    msg = str(exc.orig) if exc.orig else str(exc)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return JSONResponse(status_code=409, content={"detail": "Запись с такими данными уже существует"})
    if "foreign key" in msg.lower() or "violates" in msg.lower():
        return JSONResponse(status_code=400, content={"detail": "Некорректная ссылка (план, деталь и т.д.)"})
    # Не раскрываем клиенту внутренние детали БД — логируем на сервере, отдаём обобщённое сообщение.
    log.warning(
        "integrity_error request_id=%s method=%s path=%s error=%s",
        _request_id(request),
        request.method,
        request.url.path,
        msg,
    )
    return JSONResponse(status_code=400, content={"detail": "Не удалось сохранить данные: нарушение целостности"})


@app.exception_handler(SQLAlchemyTimeoutError)
async def db_pool_timeout_handler(request: Request, exc: SQLAlchemyTimeoutError):
    log.exception(
        "db_pool_timeout request_id=%s method=%s path=%s pool=%s",
        _request_id(request),
        request.method,
        request.url.path,
        _pool_status(),
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "База данных перегружена: нет свободного подключения. Повторите запрос через несколько секунд.",
            "request_id": _request_id(request),
        },
        headers={"retry-after": "2"},
    )


@app.exception_handler(DBAPIError)
async def db_api_error_handler(request: Request, exc: DBAPIError):
    log.exception(
        "db_error request_id=%s method=%s path=%s pool=%s",
        _request_id(request),
        request.method,
        request.url.path,
        _pool_status(),
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "База данных временно недоступна. Повторите запрос через несколько секунд.",
            "request_id": _request_id(request),
        },
        headers={"retry-after": "2"},
    )



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
        log.exception("health_db_down pool=%s", _pool_status())
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "down", "pool": pool_snapshot()},
        )
    return {"status": "ok", "db": "up", "pool": pool_snapshot()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
