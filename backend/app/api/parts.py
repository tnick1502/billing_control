import re
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


async def _generate_part_sku(session: AsyncSession) -> str:
    """Generate next part SKU: P-001, P-002, ..."""
    result = await session.execute(select(Part.sku))
    max_num = 0
    for row in result.scalars().all():
        m = re.match(r"P-(\d+)", row.sku or "", re.IGNORECASE)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"P-{max_num + 1:03d}"


@router.post("", response_model=PartRead)
async def create_part(data: PartCreate, session: AsyncSession = Depends(get_db)):
    dump = data.model_dump()
    if not dump.get("sku") or not str(dump["sku"]).strip():
        dump["sku"] = await _generate_part_sku(session)
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
    update_data = data.model_dump(exclude_unset=True)
    update_data.pop("sku", None)  # SKU immutable
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
