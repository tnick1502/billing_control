from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mrp_bom_orders"

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


settings = Settings()
