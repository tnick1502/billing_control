from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Device,
    DeviceAlias,
    Part,
    Order,
    OrderItem,
    DeviceBomVersion,
    DeviceBomItem,
    MonthlyPlan,
    MonthlyPlanDevice,
    MonthlyPlanPart,
    Invoice,
    File,
    InvoiceFile,
    InvoicePartLink,
)


async def seed_database(session: AsyncSession) -> bool:
    """Seed database with test data. Returns True if data was seeded, False if already populated."""
    result = await session.execute(select(Device).limit(1))
    if result.scalar_one_or_none() is not None:
        return False

    # Devices
    d1 = Device(sku="DEV-001", primary_name="Датчик температуры Т-100", model="T-100", is_active=True)
    d2 = Device(sku="DEV-002", primary_name="Реле контроля РК-5", model="RK-5", is_active=True)
    d3 = Device(sku="DEV-003", primary_name="Блок питания БП-12", model="BP-12", is_active=True)
    session.add_all([d1, d2, d3])
    await session.flush()

    # Device aliases
    session.add_all([
        DeviceAlias(device_id=d1.id, alias_name="Температурный датчик"),
        DeviceAlias(device_id=d2.id, alias_name="Реле РК5"),
    ])

    # Parts
    p1 = Part(sku="P-001", name="Корпус пластиковый", uom="шт", is_active=True)
    p2 = Part(sku="P-002", name="Плата печатная", uom="шт", is_active=True)
    p3 = Part(sku="P-003", name="Резистор 10кОм", uom="шт", is_active=True)
    p4 = Part(sku="P-004", name="Конденсатор 100мкФ", uom="шт", is_active=True)
    p5 = Part(sku="P-005", name="Термопара", uom="шт", is_active=True)
    p6 = Part(sku="P-006", name="Катушка реле", uom="шт", is_active=True)
    p7 = Part(sku="P-007", name="Трансформатор 12В", uom="шт", is_active=True)
    session.add_all([p1, p2, p3, p4, p5, p6, p7])
    await session.flush()

    # BOM versions (active)
    bom1 = DeviceBomVersion(device_id=d1.id, version=1, status="active")
    bom2 = DeviceBomVersion(device_id=d2.id, version=1, status="active")
    bom3 = DeviceBomVersion(device_id=d3.id, version=1, status="active")
    session.add_all([bom1, bom2, bom3])
    await session.flush()

    # BOM items
    session.add_all([
        DeviceBomItem(bom_version_id=bom1.id, part_id=p1.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0.02")),
        DeviceBomItem(bom_version_id=bom1.id, part_id=p2.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0.01")),
        DeviceBomItem(bom_version_id=bom1.id, part_id=p3.id, qty_per_device=Decimal("5"), scrap_rate=Decimal("0.05")),
        DeviceBomItem(bom_version_id=bom1.id, part_id=p5.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0")),
        DeviceBomItem(bom_version_id=bom2.id, part_id=p1.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0.02")),
        DeviceBomItem(bom_version_id=bom2.id, part_id=p2.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0.01")),
        DeviceBomItem(bom_version_id=bom2.id, part_id=p6.id, qty_per_device=Decimal("2"), scrap_rate=Decimal("0.03")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p1.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0.02")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p2.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0.01")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p7.id, qty_per_device=Decimal("1"), scrap_rate=Decimal("0")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p4.id, qty_per_device=Decimal("4"), scrap_rate=Decimal("0.05")),
    ])

    # Orders
    o1 = Order(order_no="ORD-2025-001", status="confirmed", order_date=date(2025, 3, 1))
    o2 = Order(order_no="ORD-2025-002", status="confirmed", order_date=date(2025, 3, 5))
    session.add_all([o1, o2])
    await session.flush()

    session.add_all([
        OrderItem(order_id=o1.id, device_id=d1.id, qty=Decimal("10"), price=Decimal("1500.00")),
        OrderItem(order_id=o1.id, device_id=d2.id, qty=Decimal("5"), price=Decimal("800.00")),
        OrderItem(order_id=o2.id, device_id=d1.id, qty=Decimal("20"), price=Decimal("1450.00")),
        OrderItem(order_id=o2.id, device_id=d3.id, qty=Decimal("3"), price=Decimal("2200.00")),
    ])

    # Monthly plan (March 2025)
    plan = MonthlyPlan(month=date(2025, 3, 1), revision=1, status="draft", generated_by="seed")
    session.add(plan)
    await session.flush()

    session.add_all([
        MonthlyPlanDevice(plan_id=plan.id, device_id=d1.id, qty_total=Decimal("30"), bom_version_id=bom1.id),
        MonthlyPlanDevice(plan_id=plan.id, device_id=d2.id, qty_total=Decimal("5"), bom_version_id=bom2.id),
        MonthlyPlanDevice(plan_id=plan.id, device_id=d3.id, qty_total=Decimal("3"), bom_version_id=bom3.id),
    ])

    # Monthly plan parts (aggregated from BOM)
    session.add_all([
        MonthlyPlanPart(plan_id=plan.id, part_id=p1.id, qty_required=Decimal("38"), qty_buffered=Decimal("2"), qty_final=Decimal("40")),
        MonthlyPlanPart(plan_id=plan.id, part_id=p2.id, qty_required=Decimal("38"), qty_buffered=Decimal("2"), qty_final=Decimal("40")),
        MonthlyPlanPart(plan_id=plan.id, part_id=p3.id, qty_required=Decimal("150"), qty_buffered=Decimal("10"), qty_final=Decimal("160")),
        MonthlyPlanPart(plan_id=plan.id, part_id=p4.id, qty_required=Decimal("12"), qty_buffered=Decimal("0"), qty_final=Decimal("12")),
        MonthlyPlanPart(plan_id=plan.id, part_id=p5.id, qty_required=Decimal("30"), qty_buffered=Decimal("0"), qty_final=Decimal("30")),
        MonthlyPlanPart(plan_id=plan.id, part_id=p6.id, qty_required=Decimal("10"), qty_buffered=Decimal("0"), qty_final=Decimal("10")),
        MonthlyPlanPart(plan_id=plan.id, part_id=p7.id, qty_required=Decimal("3"), qty_buffered=Decimal("0"), qty_final=Decimal("3")),
    ])

    # Invoice
    inv = Invoice(invoice_no="INV-001", invoice_date=date(2025, 3, 10), total_amount=Decimal("50000.00"), status="received")
    session.add(inv)
    await session.flush()

    session.add_all([
        InvoicePartLink(invoice_id=inv.id, plan_id=plan.id, part_id=p1.id, qty_covered=Decimal("40"), amount_allocated=Decimal("12000.00")),
        InvoicePartLink(invoice_id=inv.id, plan_id=plan.id, part_id=p2.id, qty_covered=Decimal("40"), amount_allocated=Decimal("20000.00")),
    ])

    return True
