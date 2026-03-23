import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device, DeviceAlias
from app.schemas.common import (
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
    DeviceAliasCreate,
    DeviceAliasRead,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead])
async def list_devices(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).order_by(Device.id))
    return result.scalars().all()


async def _generate_device_sku(session: AsyncSession) -> str:
    """Generate next device SKU: DEV-001, DEV-002, ..."""
    result = await session.execute(select(Device.sku))
    max_num = 0
    for row in result.scalars().all():
        m = re.match(r"DEV-(\d+)", row.sku or "", re.IGNORECASE)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"DEV-{max_num + 1:03d}"


@router.post("", response_model=DeviceRead)
async def create_device(data: DeviceCreate, session: AsyncSession = Depends(get_db)):
    dump = data.model_dump()
    if not dump.get("sku") or not str(dump.get("sku") or "").strip():
        dump["sku"] = await _generate_device_sku(session)
    if dump.get("model") == "":
        dump["model"] = None
    device = Device(**dump)
    session.add(device)
    await session.flush()
    await session.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(device_id: int, data: DeviceUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")
    update_data = data.model_dump(exclude_unset=True)
    update_data.pop("sku", None)  # SKU immutable
    for k, v in update_data.items():
        setattr(device, k, v)
    await session.flush()
    await session.refresh(device)
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")
    await session.delete(device)
    return None


@router.get("/{device_id}/aliases", response_model=list[DeviceAliasRead])
async def list_device_aliases(device_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceAlias).where(DeviceAlias.device_id == device_id))
    return result.scalars().all()


@router.post("/{device_id}/aliases", response_model=DeviceAliasRead)
async def create_device_alias(device_id: int, data: DeviceAliasCreate, session: AsyncSession = Depends(get_db)):
    alias = DeviceAlias(device_id=device_id, alias_name=data.alias_name)
    session.add(alias)
    await session.flush()
    await session.refresh(alias)
    return alias


@router.delete("/{device_id}/aliases/{alias_id}", status_code=204)
async def delete_device_alias(device_id: int, alias_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(DeviceAlias).where(DeviceAlias.id == alias_id, DeviceAlias.device_id == device_id)
    )
    alias = result.scalar_one_or_none()
    if not alias:
        raise HTTPException(404, "Alias not found")
    await session.delete(alias)
    return None
