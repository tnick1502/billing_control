from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderItem, DeviceBomVersion, DeviceBomItem, MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart


async def generate_monthly_plan(
    session: AsyncSession,
    month: date,
    order_status: str | None = "confirmed",
) -> MonthlyPlan:
    """Generate monthly plan from orders for the given month."""
    first_day = date(month.year, month.month, 1)
    _, last_day_num = monthrange(month.year, month.month)
    last_day = date(month.year, month.month, last_day_num)

    # Get orders in date range
    orders_q = select(Order).where(
        Order.order_date >= first_day,
        Order.order_date <= last_day,
    )
    if order_status:
        orders_q = orders_q.where(Order.status == order_status)
    orders_result = await session.execute(orders_q)
    orders = list(orders_result.scalars().all())
    order_ids = [o.id for o in orders]

    if not order_ids:
        revision = await get_next_revision(session, month)
        plan = MonthlyPlan(month=first_day, revision=revision, status="draft", generated_by="api")
        session.add(plan)
        await session.flush()
        return plan

    # Aggregate order_items by device_id
    items_result = await session.execute(
        select(OrderItem.device_id, func.sum(OrderItem.qty).label("qty_total"))
        .where(OrderItem.order_id.in_(order_ids))
        .group_by(OrderItem.device_id)
    )
    device_totals = {row.device_id: row.qty_total for row in items_result}

    # Get active BOM for each device
    device_ids = list(device_totals.keys())
    bom_result = await session.execute(
        select(DeviceBomVersion)
        .where(
            DeviceBomVersion.device_id.in_(device_ids),
            DeviceBomVersion.status == "active",
        )
    )
    bom_by_device = {b.device_id: b for b in bom_result.scalars().all()}

    # Check for devices without active BOM
    missing = [d for d in device_ids if d not in bom_by_device]
    if missing:
        raise ValueError(f"Devices without active BOM: {missing}")

    # Create plan
    revision = await get_next_revision(session, month)
    plan = MonthlyPlan(month=first_day, revision=revision, status="draft", generated_by="api")
    session.add(plan)
    await session.flush()

    # Create monthly_plan_devices
    part_totals: dict[int, Decimal] = {}
    for device_id, qty_total in device_totals.items():
        bom = bom_by_device[device_id]
        session.add(
            MonthlyPlanDevice(
                plan_id=plan.id,
                device_id=device_id,
                qty_total=qty_total,
                bom_version_id=bom.id,
            )
        )
        # Aggregate parts from BOM
        bom_items_result = await session.execute(
            select(DeviceBomItem).where(DeviceBomItem.bom_version_id == bom.id)
        )
        for item in bom_items_result.scalars().all():
            qty = item.qty_per_device * qty_total
            if item.scrap_rate:
                qty = qty * (1 + item.scrap_rate)
            part_totals[item.part_id] = part_totals.get(item.part_id, Decimal("0")) + qty

    # Create monthly_plan_parts
    for part_id, qty_required in part_totals.items():
        session.add(
            MonthlyPlanPart(
                plan_id=plan.id,
                part_id=part_id,
                qty_required=qty_required,
                qty_buffered=Decimal("0"),
                qty_final=qty_required,
            )
        )

    return plan


async def get_next_revision(session: AsyncSession, month: date) -> int:
    """Get next revision number for the month."""
    first_day = date(month.year, month.month, 1)
    result = await session.execute(
        select(func.max(MonthlyPlan.revision)).where(MonthlyPlan.month == first_day)
    )
    max_rev = result.scalar_one_or_none()
    return (max_rev or 0) + 1
