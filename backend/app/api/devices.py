from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device, DeviceAlias
from app.models.bom import DeviceBomVersion
from app.models.monthly_plan import MonthlyPlanDevice
from app.models.order import OrderItem
from app.schemas.common import (
    DeviceArchiveUpdate,
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
    DeviceAliasCreate,
    DeviceAliasRead,
)

router = APIRouter(prefix="/devices", tags=["devices"])


async def _check_device_references(session: AsyncSession, device_id: int) -> list[str]:
    refs: list[str] = []

    order_count = await session.scalar(
        select(func.count()).where(OrderItem.device_id == device_id)
    )
    if order_count:
        refs.append(f"заказы ({order_count} шт.)")

    plan_count = await session.scalar(
        select(func.count()).where(MonthlyPlanDevice.device_id == device_id)
    )
    if plan_count:
        refs.append(f"месячные планы ({plan_count} шт.)")

    bom_count = await session.scalar(
        select(func.count()).where(DeviceBomVersion.device_id == device_id)
    )
    if bom_count:
        refs.append(f"спецификации ({bom_count} шт.)")

    return refs


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    include_archived: bool = Query(False, alias="include_archived"),
    session: AsyncSession = Depends(get_db),
):
    q = select(Device).order_by(Device.id)
    if not include_archived:
        q = q.where(Device.is_archived == False)  # noqa: E712
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", response_model=DeviceRead)
async def create_device(data: DeviceCreate, session: AsyncSession = Depends(get_db)):
    dump = data.model_dump()
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
    for k, v in update_data.items():
        setattr(device, k, v)
    await session.flush()
    await session.refresh(device)
    return device


@router.patch("/{device_id}/archive", response_model=DeviceRead)
async def archive_device(device_id: int, data: DeviceArchiveUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")
    device.is_archived = data.is_archived
    await session.flush()
    await session.refresh(device)
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(404, "Device not found")
    refs = await _check_device_references(session, device_id)
    if refs:
        refs_str = ", ".join(refs)
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить прибор: он используется в {refs_str}. Используйте архивирование.",
        )
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
