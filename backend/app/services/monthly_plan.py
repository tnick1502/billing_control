from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Order,
    OrderItem,
    OrderPartItem,
    DeviceBomVersion,
    DeviceBomItem,
    InvoicePartLink,
    MonthlyPlan,
    MonthlyPlanDevice,
    MonthlyPlanPart,
)


async def generate_monthly_plan(
    session: AsyncSession,
    month: date,
    order_status: str | None = None,
    replace: bool = True,
) -> MonthlyPlan:
    """Generate monthly plan from orders for the given month."""
    first_day = date(month.year, month.month, 1)
    _, last_day_num = monthrange(month.year, month.month)
    last_day = date(month.year, month.month, last_day_num)

    # При replace: сохранить «поставлено» и привязки счетов, затем удалить старые планы месяца
    delivered_by_part: dict[int, Decimal] = {}
    links_snapshot: list[tuple[int, int, Decimal | None, Decimal | None, str | None]] = []

    if replace:
        existing_result = await session.execute(select(MonthlyPlan).where(MonthlyPlan.month == first_day))
        existing_plans = list(existing_result.scalars().all())
        plan_ids = [p.id for p in existing_plans]

        if plan_ids:
            pp_res = await session.execute(select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id.in_(plan_ids)))
            for pp in pp_res.scalars().all():
                prev = delivered_by_part.get(pp.part_id, Decimal("0"))
                delivered_by_part[pp.part_id] = max(prev, pp.qty_delivered)

            lk_res = await session.execute(
                select(
                    InvoicePartLink.invoice_id,
                    InvoicePartLink.part_id,
                    InvoicePartLink.qty_covered,
                    InvoicePartLink.amount_allocated,
                    InvoicePartLink.note,
                ).where(InvoicePartLink.plan_id.in_(plan_ids))
            )
            seen_ip: set[tuple[int, int]] = set()
            for row in lk_res.all():
                key = (row.invoice_id, row.part_id)
                if key not in seen_ip:
                    seen_ip.add(key)
                    links_snapshot.append(
                        (row.invoice_id, row.part_id, row.qty_covered, row.amount_allocated, row.note)
                    )

        for plan in existing_plans:
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
    active_result = await session.execute(
        select(DeviceBomVersion).where(DeviceBomVersion.status == "active")
    )
    bom_by_device = {b.device_id: b for b in active_result.scalars().all()}
    current_result = await session.execute(
        select(DeviceBomVersion).where(DeviceBomVersion.status == "current")
    )
    for b in current_result.scalars().all():
        if b.device_id not in bom_by_device:
            bom_by_device[b.device_id] = b

    all_boms_result = await session.execute(
        select(DeviceBomVersion).order_by(DeviceBomVersion.device_id, DeviceBomVersion.version)
    )
    first_bom_by_device: dict[int, DeviceBomVersion] = {}
    for b in all_boms_result.scalars().all():
        if b.device_id not in first_bom_by_device:
            first_bom_by_device[b.device_id] = b

    # Aggregate by (device_id, bom_version_id)
    device_bom_totals: dict[tuple[int, int], Decimal] = {}
    for oi in order_items:
        bom = oi.bom_version if oi.bom_version_id else bom_by_device.get(oi.device_id) or first_bom_by_device.get(oi.device_id)
        if not bom:
            raise ValueError(f"Прибор {oi.device_id} не имеет спецификации. Создайте BOM для прибора или укажите спецификацию в позиции заказа.")
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

    # Create monthly_plan_parts (поставлено переносим с прошлого плана, не больше нового «требуется»)
    for part_id, qty_required in part_totals.items():
        prev_del = delivered_by_part.get(part_id, Decimal("0"))
        qty_del = min(prev_del, qty_required)
        session.add(
            MonthlyPlanPart(
                plan_id=plan.id,
                part_id=part_id,
                qty_required=qty_required,
                qty_final=qty_required,
                qty_delivered=qty_del,
            )
        )

    await session.flush()

    # Восстановить привязки счёт → деталь в плане (только детали, которые есть в новом расчёте)
    new_part_ids = set(part_totals.keys())
    for invoice_id, part_id, qty_covered, amount_allocated, note in links_snapshot:
        if part_id not in new_part_ids:
            continue
        session.add(
            InvoicePartLink(
                invoice_id=invoice_id,
                plan_id=plan.id,
                part_id=part_id,
                qty_covered=qty_covered,
                amount_allocated=amount_allocated,
                note=note,
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
