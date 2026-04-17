import io
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Device,
    DeviceAlias,
    Part,
    Order,
    OrderItem,
    OrderPartItem,
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
from app.services.s3_service import upload_file


async def clear_database(session: AsyncSession) -> None:
    """Truncate all tables in correct order."""
    await session.execute(text(
        "TRUNCATE TABLE invoice_files, invoice_part_links, monthly_plan_part_files, "
        "monthly_plan_parts, monthly_plan_devices, monthly_plans, "
        "order_part_items, order_items, orders, "
        "device_bom_items, device_bom_versions, device_aliases, "
        "invoices, files, devices, parts RESTART IDENTITY CASCADE"
    ))
    await session.flush()


async def seed_database(session: AsyncSession, force: bool = False) -> bool:
    """Seed database with test data. Returns True if data was seeded, False if already populated."""
    result = await session.execute(select(Device).limit(1))
    already_populated = result.scalar_one_or_none() is not None
    if already_populated and not force:
        return False
    if already_populated and force:
        await clear_database(session)

    # Devices
    d1 = Device(primary_name="Датчик температуры Т-100", model="T-100", description="Промышленный датчик температуры", is_active=True)
    d2 = Device(primary_name="Реле контроля РК-5", model="RK-5", description="Реле контроля напряжения", is_active=True)
    d3 = Device(primary_name="Блок питания БП-12", model="BP-12", description="Блок питания 12В", is_active=True)
    session.add_all([d1, d2, d3])
    await session.flush()

    # Device aliases
    session.add_all([
        DeviceAlias(device_id=d1.id, alias_name="Температурный датчик"),
        DeviceAlias(device_id=d2.id, alias_name="Реле РК5"),
    ])

    # Parts
    p1 = Part(name="Корпус пластиковый", description="Ударопрочный корпус", is_active=True)
    p2 = Part(name="Плата печатная", description="Основная плата", is_active=True)
    p3 = Part(name="Резистор 10кОм", description="Точность 1%", is_active=True)
    p4 = Part(name="Конденсатор 100мкФ", description="Электролитический", is_active=True)
    p5 = Part(name="Термопара", description="Тип K", is_active=True)
    p6 = Part(name="Катушка реле", description="12В", is_active=True)
    p7 = Part(name="Трансформатор 12В", description="Мощность 5Вт", is_active=True)
    session.add_all([p1, p2, p3, p4, p5, p6, p7])
    await session.flush()

    # BOM versions (active) — по одному активному на прибор
    bom1 = DeviceBomVersion(device_id=d1.id, name="Спецификация v1", description="Базовая конфигурация", version=1, status="active")
    bom2 = DeviceBomVersion(device_id=d2.id, name="Спецификация v1", description="Стандартная комплектация", version=1, status="active")
    bom3 = DeviceBomVersion(device_id=d3.id, name="Спецификация v1", description="Полный комплект", version=1, status="active")
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

    # Orders — январь / февраль / март: разные даты, приборы и прямые детали (для графиков и тестов)
    o_jan1 = Order(status="confirmed", order_date=date(2026, 1, 8), description="Январь: датчики и реле")
    o_jan2 = Order(status="draft", order_date=date(2026, 1, 15), description="Январь: черновик по блокам питания")
    o_jan3 = Order(status="confirmed", order_date=date(2026, 1, 22), description="Январь: смешанная партия")
    o_jan4 = Order(status="confirmed", order_date=date(2026, 1, 28), description="Январь: только прямые детали")
    o_feb1 = Order(status="confirmed", order_date=date(2026, 2, 5), description="Февраль: первая волна")
    o_feb2 = Order(status="confirmed", order_date=date(2026, 2, 12), description="Февраль: реле отдельной строкой")
    o_feb3 = Order(status="confirmed", order_date=date(2026, 2, 19), description="Февраль: все три прибора")
    o_feb4 = Order(status="confirmed", order_date=date(2026, 2, 26), description="Февраль: детали без приборов")
    o1 = Order(status="confirmed", order_date=date(2026, 3, 1), description="Заказ для производства")
    o2 = Order(status="confirmed", order_date=date(2026, 3, 5), description="Дополнительная партия")
    session.add_all([o_jan1, o_jan2, o_jan3, o_jan4, o_feb1, o_feb2, o_feb3, o_feb4, o1, o2])
    await session.flush()

    # Позиции с прибором (активная BOM)
    session.add_all([
        # Январь
        OrderItem(order_id=o_jan1.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("12"), price=Decimal("1520.00")),
        OrderItem(order_id=o_jan1.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("6"), price=Decimal("790.00")),
        OrderItem(order_id=o_jan2.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("4"), price=Decimal("2180.00")),
        OrderItem(order_id=o_jan3.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("8"), price=Decimal("1510.00")),
        OrderItem(order_id=o_jan3.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("3"), price=Decimal("805.00")),
        OrderItem(order_id=o_jan3.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("2"), price=Decimal("2190.00")),
        # Февраль
        OrderItem(order_id=o_feb1.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("15"), price=Decimal("1490.00")),
        OrderItem(order_id=o_feb1.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("7"), price=Decimal("2210.00")),
        OrderItem(order_id=o_feb2.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("11"), price=Decimal("795.00")),
        OrderItem(order_id=o_feb3.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("5"), price=Decimal("1500.00")),
        OrderItem(order_id=o_feb3.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("5"), price=Decimal("800.00")),
        OrderItem(order_id=o_feb3.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("4"), price=Decimal("2200.00")),
        # Март (как было)
        OrderItem(order_id=o1.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("10"), price=Decimal("1500.00")),
        OrderItem(order_id=o1.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("5"), price=Decimal("800.00")),
        OrderItem(order_id=o2.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("20"), price=Decimal("1450.00")),
        OrderItem(order_id=o2.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("3"), price=Decimal("2200.00")),
    ])
    # Прямые позиции деталей (без прибора)
    session.add_all([
        OrderPartItem(order_id=o_jan4.id, part_id=p3.id, qty=Decimal("200"), price=Decimal("2.50"), note="Резисторы оптом"),
        OrderPartItem(order_id=o_jan4.id, part_id=p2.id, qty=Decimal("25"), price=Decimal("450.00")),
        OrderPartItem(order_id=o_feb4.id, part_id=p1.id, qty=Decimal("40"), price=Decimal("85.00")),
        OrderPartItem(order_id=o_feb4.id, part_id=p4.id, qty=Decimal("60"), price=Decimal("12.00"), note="Конденсаторы на склад"),
    ])

    # Monthly plan (March 2026)
    plan = MonthlyPlan(month=date(2026, 3, 1), revision=1, status="draft", generated_by="seed")
    session.add(plan)
    await session.flush()

    session.add_all([
        MonthlyPlanDevice(plan_id=plan.id, device_id=d1.id, qty_total=Decimal("30"), bom_version_id=bom1.id),
        MonthlyPlanDevice(plan_id=plan.id, device_id=d2.id, qty_total=Decimal("5"), bom_version_id=bom2.id),
        MonthlyPlanDevice(plan_id=plan.id, device_id=d3.id, qty_total=Decimal("3"), bom_version_id=bom3.id),
    ])

    # Monthly plan parts (aggregated from BOM)
    session.add_all([
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p1.id, qty_required=Decimal("38"), qty_final=Decimal("38"), qty_delivered=Decimal("0")
        ),
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p2.id, qty_required=Decimal("38"), qty_final=Decimal("38"), qty_delivered=Decimal("0")
        ),
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p3.id, qty_required=Decimal("150"), qty_final=Decimal("150"), qty_delivered=Decimal("0")
        ),
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p4.id, qty_required=Decimal("12"), qty_final=Decimal("12"), qty_delivered=Decimal("0")
        ),
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p5.id, qty_required=Decimal("30"), qty_final=Decimal("30"), qty_delivered=Decimal("0")
        ),
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p6.id, qty_required=Decimal("10"), qty_final=Decimal("10"), qty_delivered=Decimal("0")
        ),
        MonthlyPlanPart(
            plan_id=plan.id, part_id=p7.id, qty_required=Decimal("3"), qty_final=Decimal("3"), qty_delivered=Decimal("0")
        ),
    ])

    # Invoice
    inv = Invoice(invoice_no="tmp-seed", invoice_date=date(2026, 3, 10), total_amount=Decimal("50000.00"), status="received", description="Демо-счёт")
    session.add(inv)
    await session.flush()
    inv.invoice_no = str(inv.id)

    session.add_all([
        InvoicePartLink(invoice_id=inv.id, plan_id=plan.id, part_id=p1.id, qty_covered=Decimal("38"), amount_allocated=Decimal("12000.00")),
        InvoicePartLink(invoice_id=inv.id, plan_id=plan.id, part_id=p2.id, qty_covered=Decimal("38"), amount_allocated=Decimal("20000.00")),
    ])

    # Test invoice file (demo)
    content = b"Testovyy schet INV-001\n\nUslovnyy schet dlya demonstratsii raboty.\nData: 10.03.2026\nSumma: 50000 RUB"
    obj_key, etag, size = await upload_file(
        io.BytesIO(content),
        "INV-001-schet.pdf",
        "application/pdf",
        prefix="invoices",
    )
    db_file = File(
        storage="s3",
        bucket=settings.s3_bucket,
        object_key=obj_key,
        etag=etag,
        content_type="application/pdf",
        size_bytes=size,
    )
    session.add(db_file)
    await session.flush()
    session.add(InvoiceFile(invoice_id=inv.id, file_id=db_file.id, role="original"))

    return True
