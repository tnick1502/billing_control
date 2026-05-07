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

    await generate_test_data(session)
    return True


async def generate_test_data(session: AsyncSession) -> None:
    """Generate test data for an empty database."""
    # Devices
    d1 = Device(primary_name="Датчик температуры Т-100", model="T-100", description="Промышленный датчик температуры")
    d2 = Device(primary_name="Реле контроля РК-5", model="RK-5", description="Реле контроля напряжения")
    d3 = Device(primary_name="Блок питания БП-12", model="BP-12", description="Блок питания 12В")
    session.add_all([d1, d2, d3])
    await session.flush()

    # Device aliases
    session.add_all([
        DeviceAlias(device_id=d1.id, alias_name="Температурный датчик"),
        DeviceAlias(device_id=d2.id, alias_name="Реле РК5"),
    ])

    # Parts
    p1 = Part(name="Корпус пластиковый", cipher="KP-001", article="ART-1001", description="Ударопрочный корпус")
    p2 = Part(name="Плата печатная", cipher="PCB-001", article="ART-1002", description="Основная плата")
    p3 = Part(name="Резистор 10кОм", cipher="R-10K", article="ART-1003", description="Точность 1%")
    p4 = Part(name="Конденсатор 100мкФ", cipher="C-100UF", article="ART-1004", description="Электролитический")
    p5 = Part(name="Термопара", cipher="TC-K", article="ART-1005", description="Тип K")
    p6 = Part(name="Катушка реле", cipher="RC-12V", article="ART-1006", description="12В")
    p7 = Part(name="Трансформатор 12В", cipher="TR-12V", article="ART-1007", description="Мощность 5Вт")
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
    o_jan1 = Order(order_date=date(2026, 1, 8), customer="ООО Альфа", contract_no="Д-2026-01", description="Январь: датчики и реле")
    o_jan2 = Order(order_date=date(2026, 1, 15), customer="ООО Бета", contract_no="Д-2026-02", description="Январь: партия по блокам питания")
    o_jan3 = Order(order_date=date(2026, 1, 22), customer="АО Вектор", contract_no="Д-2026-03", description="Январь: смешанная партия")
    o_jan4 = Order(order_date=date(2026, 1, 28), customer="ООО Альфа", contract_no="Д-2026-04", description="Январь: только прямые детали")
    o_feb1 = Order(order_date=date(2026, 2, 5), customer="ООО Гамма", contract_no="Д-2026-05", description="Февраль: первая волна")
    o_feb2 = Order(order_date=date(2026, 2, 12), customer="АО Вектор", contract_no="Д-2026-06", description="Февраль: реле отдельной строкой")
    o_feb3 = Order(order_date=date(2026, 2, 19), customer="ООО Бета", contract_no="Д-2026-07", description="Февраль: все три прибора")
    o_feb4 = Order(order_date=date(2026, 2, 26), customer="ООО Гамма", contract_no="Д-2026-08", description="Февраль: детали без приборов")
    o1 = Order(order_date=date(2026, 3, 1), customer="ООО Альфа", contract_no="Д-2026-09", description="Заказ для производства")
    o2 = Order(order_date=date(2026, 3, 5), customer="АО Вектор", contract_no="Д-2026-10", description="Дополнительная партия")
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

    # Invoices: two invoices cover the same plan position to demonstrate split coverage.
    inv = Invoice(
        invoice_no="INV-001",
        invoice_date=date(2026, 3, 10),
        supplier="ООО Поставщик",
        total_amount=Decimal("39000.00"),
        payment_date=date(2026, 3, 15),
        description="Демо-счёт",
    )
    inv2 = Invoice(
        invoice_no="INV-002",
        invoice_date=date(2026, 3, 12),
        supplier="АО Комплект",
        total_amount=Decimal("11000.00"),
        payment_date=None,
        description="Демо-счёт: допоставка",
    )
    session.add_all([inv, inv2])
    await session.flush()

    session.add_all([
        InvoicePartLink(invoice_id=inv.id, plan_id=plan.id, part_id=p1.id, qty_covered=Decimal("20")),
        InvoicePartLink(invoice_id=inv.id, plan_id=plan.id, part_id=p2.id, qty_covered=Decimal("38")),
        InvoicePartLink(invoice_id=inv2.id, plan_id=plan.id, part_id=p1.id, qty_covered=Decimal("18")),
    ])

    # Test invoice files (demo)
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

    content2 = b"Testovyy schet INV-002\n\nDopolnitelnyy schet dlya demonstratsii razbitogo pokrytiya.\nData: 12.03.2026\nSumma: 11000 RUB"
    obj_key2, etag2, size2 = await upload_file(
        io.BytesIO(content2),
        "INV-002-schet.pdf",
        "application/pdf",
        prefix="invoices",
    )
    db_file2 = File(
        storage="s3",
        bucket=settings.s3_bucket,
        object_key=obj_key2,
        etag=etag2,
        content_type="application/pdf",
        size_bytes=size2,
    )
    session.add(db_file2)
    await session.flush()
    session.add(InvoiceFile(invoice_id=inv2.id, file_id=db_file2.id, role="original"))

    return None
