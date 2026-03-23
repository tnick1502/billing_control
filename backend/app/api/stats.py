"""Статистика по заказам для графиков."""

from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Device, DeviceBomItem, Order, OrderItem, OrderPartItem, Part

router = APIRouter(prefix="/stats", tags=["stats"])


def _normalize_month_start(value: date | datetime) -> date:
    """Первая дата месяца из значения БД (date или datetime от date_trunc)."""
    d = value.date() if isinstance(value, datetime) else value
    return date(d.year, d.month, 1)


@router.get("/orders-devices-timeseries")
async def orders_devices_timeseries(
    date_from: date = Query(..., description="Начало периода (включительно)"),
    date_to: date = Query(..., description="Конец периода (включительно)"),
    session: AsyncSession = Depends(get_db),
):
    """
    Сумма количества по позициям заказов (приборы) по календарному месяцу и прибору.
    Все заказы за месяц (например, весь март) суммируются в одну точку на графике.
    Формат удобен для Chart.js (labels + datasets).
    """
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="Дата начала не может быть позже даты конца")

    # PostgreSQL: группировка по месяцу (date_trunc)
    month_bucket = func.date_trunc("month", Order.order_date).label("month_bucket")

    stmt = (
        select(month_bucket, OrderItem.device_id, func.sum(OrderItem.qty).label("qty"))
        .select_from(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.order_date >= date_from, Order.order_date <= date_to)
        .group_by(month_bucket, OrderItem.device_id)
        .order_by(month_bucket, OrderItem.device_id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"labels": [], "datasets": []}

    month_starts = {_normalize_month_start(r[0]) for r in rows}
    labels = sorted(month_starts)

    device_ids = sorted({r[1] for r in rows})
    dev_result = await session.execute(select(Device.id, Device.primary_name).where(Device.id.in_(device_ids)))
    id_to_name = {d.id: d.primary_name for d in dev_result.all()}

    # (month_start, device_id) -> qty
    cell: dict[tuple[date, int], float] = defaultdict(float)
    for month_val, did, qty in rows:
        m0 = _normalize_month_start(month_val)
        cell[(m0, did)] += float(qty)

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

    by_date: dict[date, float] = defaultdict(float)

    # Прямые строки заказа (деталь как позиция)
    stmt_direct = (
        select(Order.order_date, func.sum(OrderPartItem.qty).label("qty"))
        .select_from(OrderPartItem)
        .join(Order, OrderPartItem.order_id == Order.id)
        .where(
            OrderPartItem.part_id == part_id,
            Order.order_date >= date_from,
            Order.order_date <= date_to,
        )
        .group_by(Order.order_date)
    )
    for od, qty in (await session.execute(stmt_direct)).all():
        by_date[od] += float(qty)

    # Через заказы приборов × BOM (qty приборов × qty_per_device в спецификации)
    stmt_bom = (
        select(
            Order.order_date,
            func.sum(OrderItem.qty * DeviceBomItem.qty_per_device).label("qty"),
        )
        .select_from(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .join(DeviceBomItem, DeviceBomItem.bom_version_id == OrderItem.bom_version_id)
        .where(
            OrderItem.bom_version_id.isnot(None),
            DeviceBomItem.part_id == part_id,
            Order.order_date >= date_from,
            Order.order_date <= date_to,
        )
        .group_by(Order.order_date)
    )
    for od, qty in (await session.execute(stmt_bom)).all():
        by_date[od] += float(qty)

    labels_sorted = sorted(by_date.keys())
    labels = [d.isoformat() for d in labels_sorted]
    data = [round(by_date[d], 3) for d in labels_sorted]

    return {
        "part_id": part_id,
        "part_name": part.name,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "labels": labels,
        "datasets": [
            {
                "label": f"Всего: {part.name} (прямые заказы + по BOM в заказах приборов)",
                "data": data,
                "borderColor": "rgb(245, 158, 11)",
                "backgroundColor": "rgba(245, 158, 11, 0.2)",
            }
        ],
    }
