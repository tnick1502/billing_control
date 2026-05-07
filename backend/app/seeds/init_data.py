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
    Invoice,
    File,
    InvoiceFile,
    InvoicePartLink,
)
from app.services.monthly_plan import generate_monthly_plan
from app.services.s3_service import upload_file


async def clear_database(session: AsyncSession) -> None:
    """Truncate all tables in correct order."""
    await session.execute(text(
        "TRUNCATE TABLE invoice_files, invoice_part_links, monthly_plan_part_files, "
        "monthly_plan_parts, monthly_plan_devices, monthly_plans, "
        "order_part_items, order_items, orders, "
        "device_bom_items, device_bom_versions, device_aliases, "
        "invoices, files, audit_logs, users, devices, parts RESTART IDENTITY CASCADE"
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
        DeviceBomItem(bom_version_id=bom1.id, part_id=p1.id, qty_per_device=1, scrap_rate=Decimal("0.02")),
        DeviceBomItem(bom_version_id=bom1.id, part_id=p2.id, qty_per_device=1, scrap_rate=Decimal("0.01")),
        DeviceBomItem(bom_version_id=bom1.id, part_id=p3.id, qty_per_device=5, scrap_rate=Decimal("0.05")),
        DeviceBomItem(bom_version_id=bom1.id, part_id=p5.id, qty_per_device=1, scrap_rate=Decimal("0")),
        DeviceBomItem(bom_version_id=bom2.id, part_id=p1.id, qty_per_device=1, scrap_rate=Decimal("0.02")),
        DeviceBomItem(bom_version_id=bom2.id, part_id=p2.id, qty_per_device=1, scrap_rate=Decimal("0.01")),
        DeviceBomItem(bom_version_id=bom2.id, part_id=p6.id, qty_per_device=2, scrap_rate=Decimal("0.03")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p1.id, qty_per_device=1, scrap_rate=Decimal("0.02")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p2.id, qty_per_device=1, scrap_rate=Decimal("0.01")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p7.id, qty_per_device=1, scrap_rate=Decimal("0")),
        DeviceBomItem(bom_version_id=bom3.id, part_id=p4.id, qty_per_device=4, scrap_rate=Decimal("0.05")),
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

    # Массовые заказы для проверки календарей, списков, поиска и месячной статистики.
    customers = [
        "ООО Альфа",
        "АО Вектор",
        "ООО Бета",
        "ООО Гамма",
        "ЗАО Импульс",
        "ООО Север",
        "АО Контур",
        "ООО Прогресс",
    ]
    device_configs = [
        (d1, bom1, Decimal("1480.00")),
        (d2, bom2, Decimal("820.00")),
        (d3, bom3, Decimal("2240.00")),
    ]
    direct_parts = [
        (p1, Decimal("92.00")),
        (p2, Decimal("460.00")),
        (p3, Decimal("2.70")),
        (p4, Decimal("13.50")),
        (p5, Decimal("310.00")),
        (p6, Decimal("185.00")),
        (p7, Decimal("720.00")),
    ]
    bulk_orders: list[Order] = []
    for idx in range(120):
        month = 3 if idx < 60 else 4
        month_label = "Март" if month == 3 else "Апрель"
        day = (idx % 28) + 1
        bulk_orders.append(
            Order(
                order_date=date(2026, month, day),
                customer=customers[idx % len(customers)],
                contract_no=f"Д-2026-{idx + 11:03d}",
                description=f"{month_label}: тестовый производственный заказ #{idx + 1}",
            )
        )

    session.add_all(bulk_orders)
    await session.flush()

    bulk_order_items: list[OrderItem] = []
    bulk_part_items: list[OrderPartItem] = []
    for idx, order in enumerate(bulk_orders):
        device, bom, base_price = device_configs[idx % len(device_configs)]
        qty = Decimal(str((idx % 9) + 1))
        bulk_order_items.append(
            OrderItem(
                order_id=order.id,
                device_id=device.id,
                bom_version_id=bom.id,
                qty=qty,
                price=base_price + Decimal(str((idx % 5) * 25)),
            )
        )

        if idx % 4 == 0:
            second_device, second_bom, second_price = device_configs[(idx + 1) % len(device_configs)]
            bulk_order_items.append(
                OrderItem(
                    order_id=order.id,
                    device_id=second_device.id,
                    bom_version_id=second_bom.id,
                    qty=Decimal(str((idx % 4) + 1)),
                    price=second_price,
                )
            )

        if idx % 3 == 0:
            part, price = direct_parts[idx % len(direct_parts)]
            bulk_part_items.append(
                OrderPartItem(
                    order_id=order.id,
                    part_id=part.id,
                    qty=Decimal(str(((idx % 10) + 1) * 3)),
                    price=price,
                    note="Тестовая прямая позиция детали",
                )
            )

    session.add_all(bulk_order_items + bulk_part_items)
    await session.flush()

    # Monthly plans (March and April 2026) generated from the larger order set.
    plan = await generate_monthly_plan(session, date(2026, 3, 1), replace=True)
    april_plan = await generate_monthly_plan(session, date(2026, 4, 1), replace=True)

    # 30 invoices for March and April: paid and unpaid examples for the calendar.
    suppliers = [
        "ООО Поставщик",
        "АО Комплект",
        "ООО Метиз",
        "ЗАО Электрон",
        "ООО Пластик-Снаб",
        "АО Кабель",
    ]
    invoice_parts = [p1, p2, p3, p4, p5, p6, p7]
    invoices_bulk: list[Invoice] = []
    for idx in range(30):
        invoice_month = 3 if idx < 15 else 4
        invoice_day = (idx * 2 % 27) + 1
        payment_day = min(invoice_day + 4, 28)
        invoices_bulk.append(
            Invoice(
                invoice_no=f"INV-2026-{idx + 1:03d}",
                invoice_date=date(2026, invoice_month, invoice_day),
                supplier=suppliers[idx % len(suppliers)],
                total_amount=Decimal(str(18000 + idx * 1375)) + Decimal("0.50"),
                payment_date=date(2026, invoice_month, payment_day) if idx % 3 != 1 else None,
                description=f"Тестовый счёт за {'март' if invoice_month == 3 else 'апрель'} #{idx + 1}",
            )
        )

    session.add_all(invoices_bulk)
    await session.flush()

    invoice_links: list[InvoicePartLink] = []
    for idx, invoice in enumerate(invoices_bulk):
        target_plan = plan if invoice.invoice_date.month == 3 else april_plan
        part = invoice_parts[idx % len(invoice_parts)]
        invoice_links.append(
            InvoicePartLink(
                invoice_id=invoice.id,
                plan_id=target_plan.id,
                part_id=part.id,
                qty_covered=Decimal(str((idx % 12) + 4)),
            )
        )
        if idx % 5 == 0:
            extra_part = invoice_parts[(idx + 2) % len(invoice_parts)]
            invoice_links.append(
                InvoicePartLink(
                    invoice_id=invoice.id,
                    plan_id=target_plan.id,
                    part_id=extra_part.id,
                    qty_covered=Decimal(str((idx % 7) + 2)),
                )
            )

    session.add_all(invoice_links)

    inv = invoices_bulk[0]
    inv2 = invoices_bulk[1]

    # Test invoice files (demo)
    content = (
        f"Testovyy schet {inv.invoice_no}\n\n"
        "Uslovnyy schet dlya demonstratsii raboty.\n"
        f"Data: {inv.invoice_date.isoformat()}\n"
        f"Summa: {inv.total_amount} RUB"
    ).encode()
    obj_key, etag, size = await upload_file(
        io.BytesIO(content),
        f"{inv.invoice_no}-schet.pdf",
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

    content2 = (
        f"Testovyy schet {inv2.invoice_no}\n\n"
        "Dopolnitelnyy schet dlya demonstratsii razbitogo pokrytiya.\n"
        f"Data: {inv2.invoice_date.isoformat()}\n"
        f"Summa: {inv2.total_amount} RUB"
    ).encode()
    obj_key2, etag2, size2 = await upload_file(
        io.BytesIO(content2),
        f"{inv2.invoice_no}-schet.pdf",
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
