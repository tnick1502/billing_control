import asyncio
import logging
import ssl

from sqlalchemy import event, text
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
        # Имя с экземпляром (billing_control:prod / billing_control:dev): по нему уборщик
        # находит только «свои» старые соединения. Прочие server_settings сюда НЕ кладём:
        # неизвестный серверу параметр ломает установку соединения целиком (см. _on_connect).
        "server_settings": {"application_name": settings.db_application_name},
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

# Старое имя до введения APP_INSTANCE: соединения прошлой версии приложения тоже считаем «своими».
LEGACY_APPLICATION_NAME = "billing_control"


def _server_timeout_statements(server_major: int) -> list[str]:
    """SET-команды самоочистки на стороне PostgreSQL для одного соединения.

    - idle_in_transaction_session_timeout: зависшая транзакция не держит блокировки и слот вечно;
    - idle_session_timeout (PG 14+): «осиротевшее» после SIGKILL соединение сервер закроет сам.
      Значение больше pool_recycle, поэтому живой пул это никогда не задевает — пул сам
      пересоздаёт соединения старше pool_recycle до того, как сервер их закроет;
    - tcp_keepalives_*: сервер замечает мёртвого клиента за ~1,5 мин, а не за ~2 часа.
    """
    stmts: list[str] = []
    if settings.db_idle_in_transaction_timeout > 0:
        stmts.append(f"SET idle_in_transaction_session_timeout = '{int(settings.db_idle_in_transaction_timeout)}s'")
    if server_major >= 14:
        stmts.append(f"SET idle_session_timeout = '{int(settings.db_pool_recycle) + 300}s'")
    stmts += [
        "SET tcp_keepalives_idle = 60",
        "SET tcp_keepalives_interval = 10",
        "SET tcp_keepalives_count = 3",
    ]
    return stmts


async def _apply_server_timeouts(con) -> None:
    try:
        major = con.get_server_version().major
    except Exception:  # noqa: BLE001
        major = 0
    stmts = _server_timeout_statements(major)
    try:
        # Один round-trip до удалённой БД (simple query protocol допускает несколько команд).
        await con.execute("; ".join(stmts))
        return
    except Exception as e:  # noqa: BLE001
        log.warning("db: пакет SET не выполнен (%s) — применяю по одному", e)
    for stmt in stmts:
        try:
            await con.execute(stmt)
        except Exception as e:  # noqa: BLE001 — параметр недоступен/запрещён: просто пропускаем
            log.warning("db: не удалось выполнить «%s» — %s", stmt, e)


if settings.db_server_timeouts and engine.dialect.name == "postgresql":

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _connection_record) -> None:
        dbapi_connection.run_async(_apply_server_timeouts)


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


async def reap_stale_connections() -> int:
    """Закрыть на сервере соединения, оставшиеся от прошлых запусков этого экземпляра.

    Вызывается ПЕРВЫМ обращением к БД при старте: соединение уборщика — первое соединение
    процесса, поэтому всё, что с тем же application_name открыто РАНЬШЕ него, принадлежит
    прошлым процессам (сравнение по часам сервера БД — без расхождения часов хостов).

    Трогаем только: свою базу, свою роль БД, своё имя приложения (+ старое имя без экземпляра),
    простаивающие сессии и «активные» дольше 2×command_timeout. Живой чужой пул (например,
    при будущем деплое без простоя) просто переподключится благодаря pool_pre_ping.
    Никогда не роняет старт: при любой ошибке — WARNING в лог и 0.
    """
    if engine.dialect.name != "postgresql":
        return 0

    async def _run() -> int:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT pid, state, application_name, pg_terminate_backend(pid) AS terminated
                        FROM pg_stat_activity
                        WHERE usename = current_user
                          AND datname = current_database()
                          AND application_name IN (:app_name, :legacy_name)
                          AND pid <> pg_backend_pid()
                          AND backend_start < (
                              SELECT backend_start FROM pg_stat_activity WHERE pid = pg_backend_pid()
                          )
                          AND (
                              state IN ('idle', 'idle in transaction', 'idle in transaction (aborted)')
                              OR (state = 'active'
                                  AND query_start < now() - make_interval(secs => :stale_active_s))
                          )
                        """
                    ),
                    {
                        "app_name": settings.db_application_name,
                        "legacy_name": LEGACY_APPLICATION_NAME,
                        "stale_active_s": float(settings.db_command_timeout * 2),
                    },
                )
            ).all()
            await conn.commit()
        terminated = [r for r in rows if r.terminated]
        if rows:
            log.warning(
                "db_reaper: найдено старых соединений %s, закрыто %s (%s)",
                len(rows),
                len(terminated),
                ", ".join(f"pid={r.pid}:{r.state}:{r.application_name}" for r in rows),
            )
        else:
            log.info("db_reaper: старых соединений %s не найдено", settings.db_application_name)
        return len(terminated)

    try:
        return await asyncio.wait_for(_run(), timeout=max(5, settings.db_connect_timeout + 5))
    except Exception as e:  # noqa: BLE001
        log.warning("db_reaper: пропущен (%s: %s) — старт продолжается", type(e).__name__, e)
        return 0


async def db_server_status() -> dict:
    """Сводка для админки: версия сервера, лимит соединений, наши соединения по состояниям."""
    async with engine.connect() as conn:
        version = (await conn.execute(text("SHOW server_version"))).scalar()
        max_conn = (await conn.execute(text("SHOW max_connections"))).scalar()
        total = (await conn.execute(text("SELECT count(*) FROM pg_stat_activity"))).scalar()
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT application_name, coalesce(state, '') AS state, count(*) AS n
                    FROM pg_stat_activity
                    WHERE usename = current_user AND datname = current_database()
                    GROUP BY 1, 2
                    ORDER BY 1, 2
                    """
                )
            )
        ).all()
    return {
        "server_version": version,
        "max_connections": int(max_conn) if max_conn is not None else None,
        "total_connections": int(total or 0),
        "application_name": settings.db_application_name,
        "own_role_connections": [
            {"application_name": r.application_name, "state": r.state, "count": int(r.n)} for r in rows
        ],
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
