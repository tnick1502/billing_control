from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import File as FileModel, InvoiceFile, MonthlyPlanPartFile

router = APIRouter(prefix="/files", tags=["files"])

# Типы, которые браузер может отрендерить как активный контент (риск хранимого XSS).
# Такие файлы всегда отдаём как бинарный поток.
_RISKY_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/xml",
    "application/xml",
    "text/javascript",
    "application/javascript",
}


def _content_disposition_attachment(filename: str) -> str:
    safe_utf8 = quote(filename, safe="")
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "'")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{safe_utf8}"


def _safe_media_type(content_type: str | None) -> str:
    if not content_type:
        return "application/octet-stream"
    if content_type.split(";")[0].strip().lower() in _RISKY_CONTENT_TYPES:
        return "application/octet-stream"
    return content_type


@router.get("/{file_id}/download")
async def download_file(file_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(FileModel).options(selectinload(FileModel.content)).where(FileModel.id == file_id)
    )
    f = result.scalar_one_or_none()
    if not f or not f.content:
        raise HTTPException(404, "File not found")

    # Отдаём только файлы, реально привязанные к счёту или строке плана (не произвольный id).
    linked = await session.scalar(
        select(
            exists().where(InvoiceFile.file_id == file_id)
        )
    ) or await session.scalar(
        select(exists().where(MonthlyPlanPartFile.file_id == file_id))
    )
    if not linked:
        raise HTTPException(404, "File not found")

    return Response(
        content=f.content.data,
        media_type=_safe_media_type(f.content_type),
        headers={
            "Content-Disposition": _content_disposition_attachment(f.filename),
            "X-Content-Type-Options": "nosniff",
        },
    )
