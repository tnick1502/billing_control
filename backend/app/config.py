from pydantic import field_validator, model_validator

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
    db_pool_size: int = 2          # постоянных соединений в пуле (на воркер)
    db_max_overflow: int = 0       # сверх пула под пик; для managed-БД безопаснее не создавать
    db_connection_budget: int = 2  # жёсткий максимум pool_size + max_overflow на воркер
    db_pool_timeout: int = 15      # сек ждать свободное соединение, затем 503
    db_pool_recycle: int = 1800    # сек, пересоздавать соединение (managed-БД закрывает простаивающие)

    # Логи приложения. LOG_REQUESTS=true пишет одну итоговую строку на каждый HTTP-запрос.
    log_level: str = "INFO"
    log_requests: bool = True

    public_origin: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost"
    seed_on_startup: bool = True
    force_reseed: bool = False
    wipe_db: bool = False

    # Сессии: токен действует 30 дней и продлевается при активности пользователя.
    session_ttl_hours: int = 24 * 30
    session_idle_renew_minutes: int = 30

    # Защита логина от перебора (in-process, на один воркер uvicorn).
    login_max_failures: int = 5
    login_failure_window_minutes: int = 5
    login_lockout_minutes: int = 15

    # Ограничение размера загружаемого вложения.
    max_upload_mb: int = 25

    @field_validator(
        "database_ssl",
        "database_ssl_verify",
        "seed_on_startup",
        "force_reseed",
        "wipe_db",
        "log_requests",
        mode="before",
    )
    @classmethod
    def coerce_env_bool_fields(cls, v: object) -> object:
        return _coerce_env_bool(v)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, v: str) -> str:
        level = v.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL должен быть DEBUG, INFO, WARNING, ERROR или CRITICAL")
        return level

    @field_validator(
        "db_connect_timeout",
        "db_command_timeout",
        "db_pool_size",
        "db_connection_budget",
        "db_pool_timeout",
        "db_pool_recycle",
    )
    @classmethod
    def positive_database_settings(cls, v: int) -> int:
        if v < 1:
            raise ValueError("значение должно быть больше нуля")
        return v

    @field_validator("session_ttl_hours", "session_idle_renew_minutes")
    @classmethod
    def positive_session_settings(cls, v: int) -> int:
        if v < 1:
            raise ValueError("значение должно быть больше нуля")
        return v

    @field_validator("db_max_overflow")
    @classmethod
    def non_negative_overflow(cls, v: int) -> int:
        if v < 0:
            raise ValueError("DB_MAX_OVERFLOW не может быть отрицательным")
        return v

    @model_validator(mode="after")
    def validate_connection_budget(self):
        requested = self.db_pool_size + self.db_max_overflow
        if requested > self.db_connection_budget:
            raise ValueError(
                "Пул PostgreSQL превышает DB_CONNECTION_BUDGET: "
                f"DB_POOL_SIZE ({self.db_pool_size}) + DB_MAX_OVERFLOW ({self.db_max_overflow}) "
                f"> {self.db_connection_budget}"
            )
        return self

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
