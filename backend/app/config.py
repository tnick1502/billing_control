from pydantic import field_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


def _coerce_env_bool(v: object) -> bool | object:
    """Docker/OS часто отдаёт строку "true"/"false"; pydantic её не всегда корректно мапит в bool."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("", "0", "false", "no", "off", "n"):
            return False
        if s in ("1", "true", "yes", "on", "y"):
            return True
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders"
    database_ssl: bool = False
    database_ssl_verify: bool = True

    # Таймауты и пул для удалённой БД: чтобы запросы падали быстро, а не висели бесконечно.
    db_connect_timeout: int = 10   # сек на установку соединения с БД
    db_command_timeout: int = 30   # сек на один запрос
    db_pool_size: int = 5          # постоянных соединений в пуле (на воркер)
    db_max_overflow: int = 5       # сверх пула под пик
    db_pool_timeout: int = 10      # сек ждать свободное соединение, затем ошибка
    db_pool_recycle: int = 1800    # сек, пересоздавать соединение (managed-БД закрывает простаивающие)

    public_origin: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost"
    seed_on_startup: bool = True
    force_reseed: bool = False
    wipe_db: bool = False

    # Сессии: скользящий срок жизни токена и порог продления (чтобы не писать в БД на каждом запросе).
    session_ttl_hours: int = 12
    session_idle_renew_minutes: int = 30

    # Защита логина от перебора (in-process, на один воркер uvicorn).
    login_max_failures: int = 5
    login_failure_window_minutes: int = 5
    login_lockout_minutes: int = 15

    # Ограничение размера загружаемого вложения.
    max_upload_mb: int = 25

    @field_validator("database_ssl", "database_ssl_verify", "seed_on_startup", "force_reseed", "wipe_db", mode="before")
    @classmethod
    def coerce_env_bool_fields(cls, v: object) -> object:
        return _coerce_env_bool(v)

    @field_validator("database_url")
    @classmethod
    def database_url_nonempty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError(
                "DATABASE_URL пустой. В .env для Docker Compose разрешены только строки вида KEY=value "
                "и комментарии, начинающиеся с # в первом символе строки."
            )
        return s


settings = Settings()
