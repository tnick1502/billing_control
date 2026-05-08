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

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders"
    database_ssl: bool = False  # env DATABASE_SSL=true — TLS к PostgreSQL (asyncpg)
    database_ssl_verify: bool = True  # false — без проверки CA (self-signed от провайдера), только с DATABASE_SSL=true

    # S3 / MinIO (endpoint — для сервера: в Docker часто http://minio:9000)
    s3_endpoint_url: str = "http://localhost:9000"
    # URL в presigned-ссылках для браузера (иначе в ссылке будет minio → DNS NXDOMAIN)
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "invoices"
    s3_region: str = "us-east-1"

    # App (PUBLIC_ORIGIN добавляется к CORS в main, если задан — удобно при доступе не с localhost)
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

    @field_validator("s3_endpoint_url", "s3_access_key", "s3_secret_key", "s3_bucket")
    @classmethod
    def s3_core_nonempty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError(
                "Пустая переменная S3 (endpoint, ключ или бакет). Проверьте .env: compose не подставляет "
                "значения, если файл с ошибкой синтаксиса или переменная не задана."
            )
        return s

    @field_validator("s3_public_endpoint_url", mode="before")
    @classmethod
    def s3_public_empty_to_none(cls, v: object):
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


settings = Settings()
