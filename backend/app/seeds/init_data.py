import json
from pathlib import Path
from datetime import date
from decimal import Decimal

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Device,
    DeviceBomItem,
    DeviceBomVersion,
    Invoice,
    InvoiceFile,
    InvoicePartLink,
    Order,
    OrderItem,
    OrderPartItem,
    Part,
)
from app.services.file_storage import save_bytes_as_file
from app.services.monthly_plan import generate_monthly_plan
from app.tools.bulk_import import parse_document, import_document as _bulk_import


_SEED_ATTACHMENT = Path(__file__).resolve().parent / "fixtures" / "sample_invoice_attachment.txt"
_IMPORT_FILE = Path(__file__).resolve().parent.parent / "tools" / "import_strick.json"


async def clear_database(session: AsyncSession) -> None:
    """Truncate all tables in correct order."""
    await session.execute(text(
        "TRUNCATE TABLE invoice_files, invoice_part_links, monthly_plan_part_files, "
        "monthly_plan_parts, monthly_plan_devices, monthly_plans, "
        "order_part_items, order_items, orders, "
        "device_bom_items, device_bom_versions, device_aliases, "
        "invoices, file_contents, files, audit_logs, users, devices, parts RESTART IDENTITY CASCADE"
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
    # Phase 1: load devices, parts and BOMs from the prepared import file
    raw = json.loads(_IMPORT_FILE.read_text(encoding="utf-8"))
    doc = parse_document(raw)
    await _bulk_import(session, doc, update_existing=False)

    # Phase 2: query imported devices with their active BOMs
    rows = (await session.execute(
        select(Device, DeviceBomVersion)
        .join(DeviceBomVersion, (DeviceBomVersion.device_id == Device.id) & (DeviceBomVersion.status == "active"))
        .order_by(Device.id)
    )).all()
    device_bom_pairs: list[tuple[Device, DeviceBomVersion]] = [(r[0], r[1]) for r in rows]

    if not device_bom_pairs:
        return

    # A few parts for direct order lines and invoice links
    sample_parts = (await session.execute(select(Part).order_by(Part.id).limit(7))).scalars().all()

    # Phase 3: named orders for January / February / March
    # Use first 2 simple devices + 1 composite device (has sub-devices in BOM) for variety
    d1, bom1 = device_bom_pairs[0]
    d2, bom2 = device_bom_pairs[min(1, len(device_bom_pairs) - 1)]

    # Find a composite device (BOM contains at least one sub-device entry)
    composite_row = (await session.execute(
        select(Device, DeviceBomVersion)
        .join(DeviceBomVersion, (DeviceBomVersion.device_id == Device.id) & (DeviceBomVersion.status == "active"))
        .where(exists(
            select(DeviceBomItem.id).where(
                DeviceBomItem.bom_version_id == DeviceBomVersion.id,
                DeviceBomItem.sub_device_id.isnot(None),
            )
        ))
        .order_by(Device.id)
        .limit(1)
    )).first()

    if composite_row:
        d3, bom3 = composite_row[0], composite_row[1]
    else:
        d3, bom3 = device_bom_pairs[min(2, len(device_bom_pairs) - 1)]

    o_jan1 = Order(order_date=date(2026, 1, 8), customer="ООО Альфа", contract_no="Д-2026-01", description="Январь: датчики и реле")
    o_jan2 = Order(order_date=date(2026, 1, 15), customer="ООО Бета", contract_no="Д-2026-02", description="Январь: партия")
    o_jan3 = Order(order_date=date(2026, 1, 22), customer="АО Вектор", contract_no="Д-2026-03", description="Январь: смешанная партия")
    o_jan4 = Order(order_date=date(2026, 1, 28), customer="ООО Альфа", contract_no="Д-2026-04", description="Январь: только прямые детали")
    o_feb1 = Order(order_date=date(2026, 2, 5), customer="ООО Гамма", contract_no="Д-2026-05", description="Февраль: первая волна")
    o_feb2 = Order(order_date=date(2026, 2, 12), customer="АО Вектор", contract_no="Д-2026-06", description="Февраль: второй прибор")
    o_feb3 = Order(order_date=date(2026, 2, 19), customer="ООО Бета", contract_no="Д-2026-07", description="Февраль: все три прибора")
    o_feb4 = Order(order_date=date(2026, 2, 26), customer="ООО Гамма", contract_no="Д-2026-08", description="Февраль: детали без приборов")
    o1 = Order(order_date=date(2026, 3, 1), customer="ООО Альфа", contract_no="Д-2026-09", description="Заказ для производства")
    o2 = Order(order_date=date(2026, 3, 5), customer="АО Вектор", contract_no="Д-2026-10", description="Дополнительная партия")
    session.add_all([o_jan1, o_jan2, o_jan3, o_jan4, o_feb1, o_feb2, o_feb3, o_feb4, o1, o2])
    await session.flush()

    session.add_all([
        # Январь
        OrderItem(order_id=o_jan1.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("12"), price=Decimal("15000.00")),
        OrderItem(order_id=o_jan1.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("6"), price=Decimal("18000.00")),
        OrderItem(order_id=o_jan2.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("4"), price=Decimal("22000.00")),
        OrderItem(order_id=o_jan3.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("8"), price=Decimal("15000.00")),
        OrderItem(order_id=o_jan3.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("3"), price=Decimal("18000.00")),
        OrderItem(order_id=o_jan3.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("2"), price=Decimal("22000.00")),
        # Февраль
        OrderItem(order_id=o_feb1.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("15"), price=Decimal("15000.00")),
        OrderItem(order_id=o_feb1.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("7"), price=Decimal("22000.00")),
        OrderItem(order_id=o_feb2.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("11"), price=Decimal("18000.00")),
        OrderItem(order_id=o_feb3.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("5"), price=Decimal("15000.00")),
        OrderItem(order_id=o_feb3.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("5"), price=Decimal("18000.00")),
        OrderItem(order_id=o_feb3.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("4"), price=Decimal("22000.00")),
        # Март
        OrderItem(order_id=o1.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("10"), price=Decimal("15000.00")),
        OrderItem(order_id=o1.id, device_id=d2.id, bom_version_id=bom2.id, qty=Decimal("5"), price=Decimal("18000.00")),
        OrderItem(order_id=o2.id, device_id=d1.id, bom_version_id=bom1.id, qty=Decimal("20"), price=Decimal("14500.00")),
        OrderItem(order_id=o2.id, device_id=d3.id, bom_version_id=bom3.id, qty=Decimal("3"), price=Decimal("22000.00")),
    ])

    # Прямые позиции деталей (без прибора)
    if len(sample_parts) >= 4:
        session.add_all([
            OrderPartItem(order_id=o_jan4.id, part_id=sample_parts[2].id, qty=Decimal("200"), price=Decimal("2.50"), note="Прямая позиция"),
            OrderPartItem(order_id=o_jan4.id, part_id=sample_parts[1].id, qty=Decimal("25"), price=Decimal("450.00")),
            OrderPartItem(order_id=o_feb4.id, part_id=sample_parts[0].id, qty=Decimal("40"), price=Decimal("85.00")),
            OrderPartItem(order_id=o_feb4.id, part_id=sample_parts[3].id, qty=Decimal("60"), price=Decimal("12.00")),
        ])

    # Phase 4: bulk orders for March and April (120 orders cycling through all imported devices)
    customers = [
        "ООО Альфа", "АО Вектор", "ООО Бета", "ООО Гамма",
        "ЗАО Импульс", "ООО Север", "АО Контур", "ООО Прогресс",
    ]
    n = len(device_bom_pairs)

    bulk_orders: list[Order] = []
    for idx in range(120):
        month = 3 if idx < 60 else 4
        day = (idx % 28) + 1
        month_label = "Март" if month == 3 else "Апрель"
        bulk_orders.append(Order(
            order_date=date(2026, month, day),
            customer=customers[idx % len(customers)],
            contract_no=f"Д-2026-{idx + 11:03d}",
            description=f"{month_label}: тестовый производственный заказ #{idx + 1}",
        ))

    session.add_all(bulk_orders)
    await session.flush()

    bulk_order_items: list[OrderItem] = []
    bulk_part_items: list[OrderPartItem] = []
    for idx, order in enumerate(bulk_orders):
        device, bom = device_bom_pairs[idx % n]
        qty = Decimal(str((idx % 9) + 1))
        bulk_order_items.append(OrderItem(
            order_id=order.id,
            device_id=device.id,
            bom_version_id=bom.id,
            qty=qty,
            price=Decimal("15000.00") + Decimal(str((idx % 5) * 500)),
        ))

        if idx % 4 == 0:
            second_device, second_bom = device_bom_pairs[(idx + 1) % n]
            bulk_order_items.append(OrderItem(
                order_id=order.id,
                device_id=second_device.id,
                bom_version_id=second_bom.id,
                qty=Decimal(str((idx % 4) + 1)),
                price=Decimal("15000.00"),
            ))

        if idx % 3 == 0 and sample_parts:
            part = sample_parts[idx % len(sample_parts)]
            bulk_part_items.append(OrderPartItem(
                order_id=order.id,
                part_id=part.id,
                qty=Decimal(str(((idx % 10) + 1) * 3)),
                price=Decimal("250.00"),
                note="Тестовая прямая позиция детали",
            ))

    session.add_all(bulk_order_items + bulk_part_items)
    await session.flush()

    # Phase 5: monthly plans
    plan = await generate_monthly_plan(session, date(2026, 3, 1), replace=True)
    april_plan = await generate_monthly_plan(session, date(2026, 4, 1), replace=True)

    # Phase 6: 30 invoices for March and April
    suppliers = [
        "ООО Поставщик", "АО Комплект", "ООО Метиз",
        "ЗАО Электрон", "ООО Пластик-Снаб", "АО Кабель",
    ]
    invoices_bulk: list[Invoice] = []
    for idx in range(30):
        invoice_month = 3 if idx < 15 else 4
        invoice_day = (idx * 2 % 27) + 1
        payment_day = min(invoice_day + 4, 28)
        invoices_bulk.append(Invoice(
            invoice_no=f"INV-2026-{idx + 1:03d}",
            invoice_date=date(2026, invoice_month, invoice_day),
            supplier=suppliers[idx % len(suppliers)],
            total_amount=Decimal(str(18000 + idx * 1375)) + Decimal("0.50"),
            payment_date=date(2026, invoice_month, payment_day) if idx % 3 != 1 else None,
            description=f"Тестовый счёт за {'март' if invoice_month == 3 else 'апрель'} #{idx + 1}",
        ))

    session.add_all(invoices_bulk)
    await session.flush()

    if sample_parts:
        invoice_links: list[InvoicePartLink] = []
        for idx, invoice in enumerate(invoices_bulk):
            target_plan = plan if invoice.invoice_date.month == 3 else april_plan
            part = sample_parts[idx % len(sample_parts)]
            invoice_links.append(InvoicePartLink(
                invoice_id=invoice.id,
                plan_id=target_plan.id,
                part_id=part.id,
                qty_covered=Decimal(str((idx % 12) + 4)),
            ))
            if idx % 5 == 0:
                extra_part = sample_parts[(idx + 2) % len(sample_parts)]
                invoice_links.append(InvoicePartLink(
                    invoice_id=invoice.id,
                    plan_id=target_plan.id,
                    part_id=extra_part.id,
                    qty_covered=Decimal(str((idx % 7) + 2)),
                ))
        session.add_all(invoice_links)

    # Invoice attachments
    sample_base = _SEED_ATTACHMENT.read_bytes()
    for inv in invoices_bulk:
        data = sample_base + b"\n---\nInvoice: " + inv.invoice_no.encode() + b"\n"
        db_file = await save_bytes_as_file(
            session,
            data=data,
            filename=f"{inv.invoice_no}-prilozhenie.txt",
            content_type="text/plain; charset=utf-8",
        )
        session.add(InvoiceFile(invoice_id=inv.id, file_id=db_file.id, role="original"))
