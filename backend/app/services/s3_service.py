import asyncio
import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config

from app.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


async def ensure_bucket_exists() -> None:
    client = get_s3_client()

    def _ensure():
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except Exception:
            client.create_bucket(Bucket=settings.s3_bucket)

    await asyncio.to_thread(_ensure)


def _upload_file_sync(file_obj: BinaryIO, filename: str, content_type: str | None) -> tuple[str, str | None, int | None]:
    """Upload file to S3. Returns (object_key, etag, size_bytes)."""
    client = get_s3_client()
    object_key = f"invoices/{uuid.uuid4().hex}/{filename}"
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


async def upload_file(file_obj: BinaryIO, filename: str, content_type: str | None = None) -> tuple[str, str | None, int | None]:
    return await asyncio.to_thread(_upload_file_sync, file_obj, filename, content_type)


def get_presigned_url(bucket: str, object_key: str, expires_in: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )


async def delete_file(bucket: str, object_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=bucket, Key=object_key)
