from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Part
from app.schemas.common import PartCreate, PartRead, PartUpdate

router = APIRouter(prefix="/parts", tags=["parts"])


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _normalize_part_payload(data: dict) -> dict:
    for key in ("name", "cipher", "article", "description"):
        if key in data:
            data[key] = _clean_text(data[key])
    return data


async def _ensure_part_unique(
    session: AsyncSession,
    name: str,
    article: str | None,
    exclude_id: int | None = None,
) -> None:
    conditions = [
        func.lower(Part.name) == name.lower(),
        func.coalesce(func.lower(Part.article), "") == (article or "").lower(),
    ]
    if exclude_id is not None:
        conditions.append(Part.id != exclude_id)

    result = await session.execute(select(Part.id).where(*conditions).limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Деталь с таким наименованием и артикулом уже существует",
        )


@router.get("", response_model=list[PartRead])
async def list_parts(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Part).order_by(Part.id))
    return result.scalars().all()


@router.post("", response_model=PartRead)
async def create_part(data: PartCreate, session: AsyncSession = Depends(get_db)):
    dump = _normalize_part_payload(data.model_dump())
    if not dump.get("name"):
        raise HTTPException(status_code=400, detail="Наименование детали обязательно")
    await _ensure_part_unique(session, dump["name"], dump.get("article"))
    part = Part(**dump)
    session.add(part)
    await session.flush()
    await session.refresh(part)
    return part


@router.get("/{part_id}", response_model=PartRead)
async def get_part(part_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    return part


@router.patch("/{part_id}", response_model=PartRead)
async def update_part(part_id: int, data: PartUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    update_data = _normalize_part_payload(data.model_dump(exclude_unset=True))
    next_name = update_data.get("name", part.name)
    next_article = update_data.get("article", part.article)
    if not next_name:
        raise HTTPException(status_code=400, detail="Наименование детали обязательно")
    await _ensure_part_unique(session, next_name, next_article, exclude_id=part.id)
    for k, v in update_data.items():
        setattr(part, k, v)
    await session.flush()
    await session.refresh(part)
    return part


@router.delete("/{part_id}", status_code=204)
async def delete_part(part_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    await session.delete(part)
    return None
