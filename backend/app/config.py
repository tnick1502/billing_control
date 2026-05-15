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

    public_origin: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost"
    seed_on_startup: bool = True
    force_reseed: bool = False

    @field_validator("database_ssl", "database_ssl_verify", "seed_on_startup", "force_reseed", mode="before")
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
