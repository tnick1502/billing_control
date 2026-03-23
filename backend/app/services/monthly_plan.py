from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, OrderPartItem, DeviceBomVersion, DeviceBomItem, MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart


async def generate_monthly_plan(
    session: AsyncSession,
    month: date,
    order_status: str | None = "confirmed",
    replace: bool = True,
) -> MonthlyPlan:
    """Generate monthly plan from orders for the given month."""
    first_day = date(month.year, month.month, 1)
    _, last_day_num = monthrange(month.year, month.month)
    last_day = date(month.year, month.month, last_day_num)

    # Replace: delete existing plan(s) for this month
    if replace:
        existing = await session.execute(select(MonthlyPlan).where(MonthlyPlan.month == first_day))
        for plan in existing.scalars().all():
            await session.delete(plan)
        await session.flush()

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
        revision = 1 if replace else await get_next_revision(session, month)
        plan = MonthlyPlan(month=first_day, revision=revision, status="draft", generated_by="api")
        session.add(plan)
        await session.flush()
        return plan

    # Get order items with resolved BOM (use bom_version_id if set, else active BOM for device)
    items_result = await session.execute(
        select(OrderItem)
        .where(OrderItem.order_id.in_(order_ids))
        .options(selectinload(OrderItem.bom_version))
    )
    order_items = list(items_result.scalars().all())
    bom_result = await session.execute(
        select(DeviceBomVersion).where(DeviceBomVersion.status == "active")
    )
    bom_by_device = {b.device_id: b for b in bom_result.scalars().all()}

    # Aggregate by (device_id, bom_version_id)
    device_bom_totals: dict[tuple[int, int], Decimal] = {}
    for oi in order_items:
        bom = oi.bom_version if oi.bom_version_id else bom_by_device.get(oi.device_id)
        if not bom:
            raise ValueError(f"Device {oi.device_id} has no BOM (set bom_version_id on order item or active BOM on device)")
        key = (oi.device_id, bom.id)
        device_bom_totals[key] = device_bom_totals.get(key, Decimal("0")) + oi.qty

    # Aggregate order_part_items (direct part orders)
    part_items_result = await session.execute(
        select(OrderPartItem.part_id, func.sum(OrderPartItem.qty).label("qty_total"))
        .where(OrderPartItem.order_id.in_(order_ids))
        .group_by(OrderPartItem.part_id)
    )
    direct_part_totals = {row.part_id: row.qty_total for row in part_items_result}

    # Create plan (revision 1 when replacing)
    revision = 1 if replace else await get_next_revision(session, month)
    plan = MonthlyPlan(month=first_day, revision=revision, status="draft", generated_by="api")
    session.add(plan)
    await session.flush()

    # Create monthly_plan_devices and aggregate parts
    part_totals: dict[int, Decimal] = {}
    for (device_id, bom_id), qty_total in device_bom_totals.items():
        session.add(
            MonthlyPlanDevice(
                plan_id=plan.id,
                device_id=device_id,
                qty_total=qty_total,
                bom_version_id=bom_id,
            )
        )
        bom_items_result = await session.execute(
            select(DeviceBomItem).where(DeviceBomItem.bom_version_id == bom_id)
        )
        for item in bom_items_result.scalars().all():
            qty = item.qty_per_device * qty_total
            part_totals[item.part_id] = part_totals.get(item.part_id, Decimal("0")) + qty

    # Add direct part orders to part_totals
    for part_id, qty in direct_part_totals.items():
        part_totals[part_id] = part_totals.get(part_id, Decimal("0")) + qty

    # Create monthly_plan_parts
    for part_id, qty_required in part_totals.items():
        session.add(
            MonthlyPlanPart(
                plan_id=plan.id,
                part_id=part_id,
                qty_required=qty_required,
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
