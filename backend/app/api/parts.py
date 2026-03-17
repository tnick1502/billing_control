from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Part
from app.schemas.common import PartCreate, PartRead, PartUpdate

router = APIRouter(prefix="/parts", tags=["parts"])


@router.get("", response_model=list[PartRead])
async def list_parts(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Part).order_by(Part.id))
    return result.scalars().all()


@router.post("", response_model=PartRead)
async def create_part(data: PartCreate, session: AsyncSession = Depends(get_db)):
    part = Part(**data.model_dump())
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
    for k, v in data.model_dump(exclude_unset=True).items():
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
