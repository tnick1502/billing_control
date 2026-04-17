import asyncio
import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config

from app.config import settings


def _client(endpoint_url: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def get_s3_client():
    """Клиент для загрузки/удаления — тот же endpoint, что видит бэкенд."""
    return _client(settings.s3_endpoint_url)


def get_s3_client_for_presign():
    """Клиент для presigned URL — хост должен открываться в браузере (localhost, не minio)."""
    public_url = settings.s3_public_endpoint_url or settings.s3_endpoint_url
    return _client(public_url)


async def ensure_bucket_exists() -> None:
    client = get_s3_client()

    def _ensure():
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            client.create_bucket(Bucket=settings.s3_bucket)

    await asyncio.to_thread(_ensure)


def _upload_file_sync(
    file_obj: BinaryIO, filename: str, content_type: str | None, prefix: str = "invoices"
) -> tuple[str, str | None, int | None]:
    """Upload file to S3. Returns (object_key, etag, size_bytes)."""
    client = get_s3_client()
    object_key = f"{prefix}/{uuid.uuid4().hex}/{filename}"
    file_obj.seek(0)
    data = file_obj.read()
    size = len(data)

    extra = {}
    if content_type:
        extra["ContentType"] = content_type

    response = client.put_object(
        Bucket=settings.s3_bucket,
        Key=object_key,
        Body=data,
        **extra,
    )
    return object_key, response.get("ETag", "").strip('"'), size


async def upload_file(
    file_obj: BinaryIO, filename: str, content_type: str | None = None, prefix: str = "invoices"
) -> tuple[str, str | None, int | None]:
    return await asyncio.to_thread(_upload_file_sync, file_obj, filename, content_type, prefix)


def get_presigned_url(bucket: str, object_key: str, expires_in: int = 3600) -> str:
    client = get_s3_client_for_presign()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )


async def delete_file(bucket: str, object_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=bucket, Key=object_key)
