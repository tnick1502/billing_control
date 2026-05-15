import logging
import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

log = logging.getLogger(__name__)


def _db_connect_args() -> dict:
    if not settings.database_ssl:
        return {}
    if settings.database_ssl_verify:
        return {"ssl": True}
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return {"ssl": ctx}


engine = create_async_engine(
    settings.database_url,
    connect_args=_db_connect_args(),
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    pool_timeout=60,
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
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            log.exception("Сессия БД: ошибка при commit или во время запроса")
            await session.rollback()
            raise
