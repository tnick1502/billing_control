from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device, DeviceBomVersion, DeviceBomItem
from app.schemas.common import (
    BomVersionCreate,
    BomVersionRead,
    BomVersionUpdate,
    BomItemCreate,
    BomItemRead,
    BomItemUpdate,
)

router = APIRouter(tags=["bom"])


@router.get("/devices/{device_id}/bom", response_model=list[BomVersionRead])
async def list_device_bom(device_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(DeviceBomVersion).where(DeviceBomVersion.device_id == device_id).order_by(DeviceBomVersion.version)
    )
    return result.scalars().all()


@router.post("/devices/{device_id}/bom", response_model=BomVersionRead)
async def create_device_bom(device_id: int, data: BomVersionCreate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.id == device_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Device not found")
    bom = DeviceBomVersion(device_id=device_id, **data.model_dump())
    session.add(bom)
    await session.flush()
    await session.refresh(bom)
    return bom


@router.get("/bom/{bom_id}", response_model=BomVersionRead)
async def get_bom(bom_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceBomVersion).where(DeviceBomVersion.id == bom_id))
    bom = result.scalar_one_or_none()
    if not bom:
        raise HTTPException(404, "BOM version not found")
    return bom


@router.patch("/bom/{bom_id}", response_model=BomVersionRead)
async def update_bom(bom_id: int, data: BomVersionUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceBomVersion).where(DeviceBomVersion.id == bom_id))
    bom = result.scalar_one_or_none()
    if not bom:
        raise HTTPException(404, "BOM version not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(bom, k, v)
    await session.flush()
    await session.refresh(bom)
    return bom


@router.delete("/bom/{bom_id}", status_code=204)
async def delete_bom(bom_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceBomVersion).where(DeviceBomVersion.id == bom_id))
    bom = result.scalar_one_or_none()
    if not bom:
        raise HTTPException(404, "BOM version not found")
    await session.delete(bom)
    return None


@router.get("/bom/{bom_id}/items", response_model=list[BomItemRead])
async def list_bom_items(bom_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceBomItem).where(DeviceBomItem.bom_version_id == bom_id))
    return result.scalars().all()


@router.post("/bom/{bom_id}/items", response_model=BomItemRead)
async def create_bom_item(bom_id: int, data: BomItemCreate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceBomVersion).where(DeviceBomVersion.id == bom_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "BOM version not found")
    item = DeviceBomItem(bom_version_id=bom_id, **data.model_dump())
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item


@router.patch("/bom/{bom_id}/items/{item_id}", response_model=BomItemRead)
async def update_bom_item(bom_id: int, item_id: int, data: BomItemUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(DeviceBomItem).where(DeviceBomItem.id == item_id, DeviceBomItem.bom_version_id == bom_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "BOM item not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await session.flush()
    await session.refresh(item)
    return item


@router.delete("/bom/{bom_id}/items/{item_id}", status_code=204)
async def delete_bom_item(bom_id: int, item_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(DeviceBomItem).where(DeviceBomItem.id == item_id, DeviceBomItem.bom_version_id == bom_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "BOM item not found")
    await session.delete(item)
    return None
