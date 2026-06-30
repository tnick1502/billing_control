from collections.abc import Iterable

from fastapi import UploadFile
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import File, FileContent, InvoiceFile, MonthlyPlanPartFile


def _check_size(num_bytes: int) -> None:
    limit = settings.max_upload_mb * 1024 * 1024
    if num_bytes > limit:
        raise ValueError(f"Файл слишком большой (> {settings.max_upload_mb} МБ)")


async def save_upload_as_file(session: AsyncSession, upload: UploadFile) -> File:
    body = await upload.read()
    if not body:
        raise ValueError("Файл пустой")
    _check_size(len(body))
    name = (upload.filename or "document").strip() or "document"
    db = File(
        filename=name,
        content_type=upload.content_type,
        size_bytes=len(body),
    )
    db.content = FileContent(data=body)
    session.add(db)
    await session.flush()
    return db


async def save_bytes_as_file(
    session: AsyncSession,
    *,
    data: bytes,
    filename: str,
    content_type: str | None,
) -> File:
    name = filename.strip() or "document"
    db = File(
        filename=name,
        content_type=content_type,
        size_bytes=len(data),
    )
    db.content = FileContent(data=data)
    session.add(db)
    await session.flush()
    return db


async def delete_orphaned_files(session: AsyncSession, file_ids: Iterable[int]) -> None:
    """Удаляет строки files/file_contents, если ни invoice_files, ни monthly_plan_part_files больше не ссылаются."""
    for fid in set(file_ids):
        still_linked_invoice = await session.scalar(select(exists().where(InvoiceFile.file_id == fid)))
        still_linked_plan = await session.scalar(select(exists().where(MonthlyPlanPartFile.file_id == fid)))
        if still_linked_invoice or still_linked_plan:
            continue
        f = await session.get(File, fid)
        if f is not None:
            await session.delete(f)
