import logging
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

log = logging.getLogger(__name__)


def _db_connect_args() -> dict:
    # asyncpg: timeout — установка соединения, command_timeout — на один запрос.
    # Без них запрос к недоступной/медленной БД висит бесконечно (отсюда зависания всей витрины).
    args: dict = {
        "timeout": settings.db_connect_timeout,
        "command_timeout": settings.db_command_timeout,
        "server_settings": {"application_name": "billing_control"},
    }
    if not settings.database_ssl:
        return args
    if settings.database_ssl_verify:
        args["ssl"] = True
        return args
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    args["ssl"] = ctx
    return args


engine = create_async_engine(
    settings.database_url,
    connect_args=_db_connect_args(),
    echo=False,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    # Последним использованным соединением пользуемся первым: остальные могут спокойно
    # простаивать и закрываться на стороне managed PostgreSQL, не раздувая число активных slots.
    pool_use_lifo=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def pool_snapshot() -> dict[str, int | str]:
    """Без подключения к БД вернуть текущее состояние локального SQLAlchemy-пула."""
    pool = engine.sync_engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        # До первого заполнения QueuePool внутренне считает незанятые базовые slots
        # отрицательным overflow; наружу отдаём понятное неотрицательное значение.
        "overflow": max(0, pool.overflow()),
        "connection_budget": settings.db_connection_budget,
    }


async def wipe_application_schema(engine) -> None:
    """
    Полный сброс схемы приложения: удаление всех таблиц из Base.metadata и создание заново.
    Удаляет все данные. Только для локальной/dev разработки — в проде не вызывать из кода.

    Перед drop загружает пакет ``app.models``, чтобы в metadata попали все таблицы.
    """
    import app.models  # noqa: F401 — регистрация всех моделей в metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("[billing_control] БД: полная пересборка схемы (drop_all + create_all) выполнена", flush=True)


async def get_db() -> AsyncSession:
    """Request transaction committed before the HTTP response becomes observable.

    Every API injection must use ``Depends(get_db, scope="function")``. FastAPI
    0.118+ otherwise runs the code after ``yield`` after sending the response,
    which breaks read-after-write when the frontend immediately refreshes a row.
    ``test_db_transaction_scope`` guards that contract for new endpoints.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            log.exception("Сессия БД: ошибка при commit или во время запроса")
            await session.rollback()
            raise
