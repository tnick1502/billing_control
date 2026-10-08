from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_policy
from app.models import File as FileModel, InvoiceFile, MonthlyPlanPartFile
from app.permissions import VIEW

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
async def download_file(file_id: int, request: Request, session: AsyncSession = Depends(get_db, scope="function")):
    policy = get_policy(request)
    # Файл может быть привязан к счёту, к плану или к обоим. Проверяем право на
    # фактическую привязку до загрузки байтов, а не только право на общий URL.
    authorized_link = False
    if policy.level("invoices") >= VIEW:
        authorized_link = bool(await session.scalar(select(exists().where(InvoiceFile.file_id == file_id))))
    if not authorized_link and policy.level("monthly_plans") >= VIEW:
        authorized_link = bool(await session.scalar(select(exists().where(MonthlyPlanPartFile.file_id == file_id))))
    if not authorized_link:
        raise HTTPException(404, "File not found")

    result = await session.execute(
        select(FileModel).options(selectinload(FileModel.content)).where(FileModel.id == file_id)
    )
    f = result.scalar_one_or_none()
    if not f or not f.content:
        raise HTTPException(404, "File not found")

    return Response(
        content=f.content.data,
        media_type=_safe_media_type(f.content_type),
        headers={
            "Content-Disposition": _content_disposition_attachment(f.filename),
            "X-Content-Type-Options": "nosniff",
        },
    )
