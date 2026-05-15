from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import File as FileModel

router = APIRouter(prefix="/files", tags=["files"])


def _content_disposition_attachment(filename: str) -> str:
    safe_utf8 = quote(filename, safe="")
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "'")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{safe_utf8}"


@router.get("/{file_id}/download")
async def download_file(file_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(FileModel).options(selectinload(FileModel.content)).where(FileModel.id == file_id)
    )
    f = result.scalar_one_or_none()
    if not f or not f.content:
        raise HTTPException(404, "File not found")
    media = f.content_type or "application/octet-stream"
    return Response(
        content=f.content.data,
        media_type=media,
        headers={"Content-Disposition": _content_disposition_attachment(f.filename)},
    )
