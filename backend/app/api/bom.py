from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device, DeviceBomVersion, DeviceBomItem
from app.models.monthly_plan import MonthlyPlanDevice
from app.models.order import OrderItem
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
    dump = data.model_dump()
    if not dump.get("name") or not str(dump.get("name") or "").strip():
        dump["name"] = f"Спецификация v{dump.get('version', 1)}"
    bom = DeviceBomVersion(device_id=device_id, **dump)
    session.add(bom)
    await session.flush()

    active_result = await session.execute(
        select(DeviceBomVersion).where(
            DeviceBomVersion.device_id == device_id,
            DeviceBomVersion.status == "active",
        )
    )
    active_bom = active_result.scalar_one_or_none()
    if active_bom:
        items_result = await session.execute(
            select(DeviceBomItem).where(DeviceBomItem.bom_version_id == active_bom.id)
        )
        for src in items_result.scalars().all():
            session.add(
                DeviceBomItem(
                    bom_version_id=bom.id,
                    part_id=src.part_id,
                    sub_device_id=src.sub_device_id,
                    sub_bom_version_id=src.sub_bom_version_id,
                    qty_per_device=src.qty_per_device,
                    scrap_rate=src.scrap_rate,
                    note=src.note,
                )
            )

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
    dump = data.model_dump(exclude_unset=True)
    if dump.get("status") == "active":
        await session.execute(
            update(DeviceBomVersion)
            .where(DeviceBomVersion.device_id == bom.device_id, DeviceBomVersion.id != bom_id)
            .values(status="archived")
        )
    elif dump.get("status") == "current":
        await session.execute(
            update(DeviceBomVersion)
            .where(
                DeviceBomVersion.device_id == bom.device_id,
                DeviceBomVersion.id != bom_id,
                DeviceBomVersion.status == "current",
            )
            .values(status="archived")
        )
    for k, v in dump.items():
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
    refs: list[str] = []
    order_count = await session.scalar(
        select(func.count()).where(OrderItem.bom_version_id == bom_id)
    )
    if order_count:
        refs.append(f"заказы ({order_count} шт.)")
    plan_count = await session.scalar(
        select(func.count()).where(MonthlyPlanDevice.bom_version_id == bom_id)
    )
    if plan_count:
        refs.append(f"месячные планы ({plan_count} шт.)")
    # Also check if this BOM is referenced as sub_bom_version_id in any BOM item
    subdev_ref_count = await session.scalar(
        select(func.count()).where(DeviceBomItem.sub_bom_version_id == bom_id)
    )
    if subdev_ref_count:
        refs.append(f"спецификации подприборов ({subdev_ref_count} шт.)")
    if refs:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить спецификацию: она используется в {', '.join(refs)}.",
        )
    await session.delete(bom)
    return None


@router.get("/bom/{bom_id}/items", response_model=list[BomItemRead])
async def list_bom_items(bom_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(DeviceBomItem).where(DeviceBomItem.bom_version_id == bom_id))
    return result.scalars().all()


@router.post("/bom/{bom_id}/items", response_model=BomItemRead)
async def create_bom_item(bom_id: int, data: BomItemCreate, session: AsyncSession = Depends(get_db)):
    bom = await session.scalar(select(DeviceBomVersion).where(DeviceBomVersion.id == bom_id))
    if not bom:
        raise HTTPException(404, "BOM version not found")

    if data.sub_device_id is not None:
        # Prevent self-reference: sub-device cannot be the same device as this BOM's device
        if data.sub_device_id == bom.device_id:
            raise HTTPException(400, "Нельзя добавить прибор в собственную спецификацию (цикл)")

        # Check that the sub_device actually exists
        sub_dev = await session.scalar(select(Device).where(Device.id == data.sub_device_id))
        if not sub_dev:
            raise HTTPException(404, "Подприбор не найден")

        # Check for duplicate sub_device_id in this BOM
        existing = await session.scalar(
            select(DeviceBomItem).where(
                DeviceBomItem.bom_version_id == bom_id,
                DeviceBomItem.sub_device_id == data.sub_device_id,
            )
        )
        if existing:
            raise HTTPException(409, f"Подприбор уже добавлен в эту спецификацию")

        # Validate sub_bom_version_id belongs to sub_device_id
        if data.sub_bom_version_id is not None:
            sub_bom = await session.scalar(
                select(DeviceBomVersion).where(
                    DeviceBomVersion.id == data.sub_bom_version_id,
                    DeviceBomVersion.device_id == data.sub_device_id,
                )
            )
            if not sub_bom:
                raise HTTPException(400, "Указанная спецификация не принадлежит выбранному подприбору")

        item = DeviceBomItem(
            bom_version_id=bom_id,
            part_id=None,
            sub_device_id=data.sub_device_id,
            sub_bom_version_id=data.sub_bom_version_id,
            qty_per_device=data.qty_per_device,
            scrap_rate=data.scrap_rate,
            note=data.note,
        )
    else:
        # Part item
        item = DeviceBomItem(
            bom_version_id=bom_id,
            part_id=data.part_id,
            sub_device_id=None,
            sub_bom_version_id=None,
            qty_per_device=data.qty_per_device,
            scrap_rate=data.scrap_rate,
            note=data.note,
        )

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
