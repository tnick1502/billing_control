from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.database import get_db
from app.models import File as FileModel
from app.services.s3_service import get_presigned_url
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}/presigned-url")
async def get_file_presigned_url(file_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(FileModel).where(FileModel.id == file_id))
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(404, "File not found")
    url = get_presigned_url(f.bucket, f.object_key)
    return {"url": url}
