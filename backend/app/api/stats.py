"""Статистика по заказам для графиков."""

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device, Order, OrderItem, OrderPartItem, Part

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/orders-devices-timeseries")
async def orders_devices_timeseries(
    date_from: date = Query(..., description="Начало периода (включительно)"),
    date_to: date = Query(..., description="Конец периода (включительно)"),
    session: AsyncSession = Depends(get_db),
):
    """
    Сумма количества по позициям заказов (приборы) по дате заказа и прибору.
    Формат удобен для Chart.js (labels + datasets).
    """
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты конца")

    stmt = (
        select(Order.order_date, OrderItem.device_id, func.sum(OrderItem.qty).label("qty"))
        .select_from(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.order_date >= date_from, Order.order_date <= date_to)
        .group_by(Order.order_date, OrderItem.device_id)
        .order_by(Order.order_date, OrderItem.device_id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"labels": [], "datasets": []}

    dates_set = {r[0] for r in rows}
    labels = sorted(dates_set)

    device_ids = sorted({r[1] for r in rows})
    dev_result = await session.execute(select(Device.id, Device.primary_name).where(Device.id.in_(device_ids)))
    id_to_name = {d.id: d.primary_name for d in dev_result.all()}

    # (date, device_id) -> qty
    cell: dict[tuple[date, int], float] = defaultdict(float)
    for od, did, qty in rows:
        cell[(od, did)] += float(qty)

    datasets = []
    # стабильные цвета для линий
    colors = [
        "rgb(245, 158, 11)",
        "rgb(52, 211, 153)",
        "rgb(96, 165, 250)",
        "rgb(232, 121, 249)",
        "rgb(251, 113, 133)",
        "rgb(163, 230, 53)",
        "rgb(45, 212, 191)",
        "rgb(251, 191, 36)",
    ]
    for idx, did in enumerate(device_ids):
        name = id_to_name.get(did, f"Прибор #{did}")
        data = [round(cell.get((lab, did), 0), 3) for lab in labels]
        c = colors[idx % len(colors)]
        bg = c.replace("rgb(", "rgba(").replace(")", ", 0.15)")
        datasets.append(
            {
                "label": name,
                "device_id": did,
                "data": data,
                "borderColor": c,
                "backgroundColor": bg,
            }
        )

    return {"labels": [d.isoformat() for d in labels], "datasets": datasets}


@router.get("/orders-parts-timeseries")
async def orders_parts_timeseries(
    part_id: int = Query(..., description="ID детали"),
    date_from: date = Query(..., description="Начало периода (включительно)"),
    date_to: date = Query(..., description="Конец периода (включительно)"),
    session: AsyncSession = Depends(get_db),
):
    """Сумма количества прямых заказов детали по дате заказа в выбранном периоде."""
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты конца")

    part = await session.scalar(select(Part).where(Part.id == part_id))
    if not part:
        raise HTTPException(status_code=404, detail="Деталь не найдена")

    stmt = (
        select(Order.order_date, func.sum(OrderPartItem.qty).label("qty"))
        .select_from(OrderPartItem)
        .join(Order, OrderPartItem.order_id == Order.id)
        .where(
            OrderPartItem.part_id == part_id,
            Order.order_date >= date_from,
            Order.order_date <= date_to,
        )
        .group_by(Order.order_date)
        .order_by(Order.order_date)
    )
    result = await session.execute(stmt)
    rows = result.all()

    labels = [r[0].isoformat() for r in rows]
    data = [round(float(r[1]), 3) for r in rows]

    return {
        "part_id": part_id,
        "part_name": part.name,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "labels": labels,
        "datasets": [
            {
                "label": f"Заказано: {part.name}",
                "data": data,
                "borderColor": "rgb(245, 158, 11)",
                "backgroundColor": "rgba(245, 158, 11, 0.2)",
            }
        ],
    }
