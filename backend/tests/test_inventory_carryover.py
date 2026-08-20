import asyncio
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api.monthly_plans import (
    _plan_parts_with_coverage,
    cancel_inventory_document,
    delete_monthly_plan,
    get_remainders,
    save_inventory_document,
    update_plan_part,
)
from app.database import Base
from app.models import (
    InventoryDocument,
    InventoryItem,
    InventoryPlanAllocation,
    Invoice,
    InvoicePartLink,
    MonthlyPlan,
    MonthlyPlanPart,
    Part,
)
from app.services.carryover import compute_carryover, recompute_carryover_links
from app.schemas.common import (
    InventoryDocumentUpsert,
    InventoryItemUpsert,
    MonthlyPlanPartUpdate,
)


def test_inventory_is_consumed_once_and_carries_forward_with_source_tracking():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                part = Part(name="Найденная деталь")
                august = MonthlyPlan(month=date(2026, 8, 1), revision=1)
                september = MonthlyPlan(month=date(2026, 9, 1), revision=1)
                invoice = Invoice(invoice_no="СФ-INV", invoice_date=date(2026, 8, 15))
                session.add_all([part, august, september, invoice])
                await session.flush()

                august_row = MonthlyPlanPart(
                    plan_id=august.id,
                    part_id=part.id,
                    qty_required=Decimal("10"),
                    qty_final=Decimal("10"),
                    # Старое значение ввели до инвентаризации. После распределения
                    # найденных 6 единиц поставка по счетам должна стать максимум 4.
                    qty_delivered=Decimal("8"),
                )
                september_row = MonthlyPlanPart(
                    plan_id=september.id,
                    part_id=part.id,
                    qty_required=Decimal("5"),
                    qty_final=Decimal("5"),
                    qty_delivered=Decimal("0"),
                )
                session.add_all([august_row, september_row])
                await session.flush()
                session.add(
                    InvoicePartLink(
                        invoice_id=invoice.id,
                        plan_id=august.id,
                        part_id=part.id,
                        qty_covered=Decimal("4"),
                        is_carryover=False,
                    )
                )
                document = InventoryDocument(month=date(2026, 8, 1), status="posted")
                session.add(document)
                await session.flush()
                item = InventoryItem(
                    inventory_id=document.id,
                    part_id=part.id,
                    qty_found=Decimal("12"),
                )
                session.add(item)
                await session.flush()

                await recompute_carryover_links(session)
                result = await compute_carryover(session)

                await session.refresh(august_row)
                assert august_row.qty_delivered == Decimal("4")

                # Август: счёт сохранил свои 4 единицы покрытия, инвентаризация
                # закрыла только недостающие 6. Из найденных 12 осталось 6;
                # сентябрь потребил ещё 5 и оставил одну физическую единицу.
                assert result.inventory_additions[part.id][date(2026, 8, 1)] == Decimal("12")
                assert result.inventory_consumed[part.id][date(2026, 8, 1)] == Decimal("6")
                assert result.inventory_consumed[part.id][date(2026, 9, 1)] == Decimal("5")
                assert result.balances[part.id][date(2026, 9, 1)] == Decimal("1")
                assert result.invoice_balances[part.id][date(2026, 9, 1)] == Decimal("0")
                assert result.inventory_balances[part.id][date(2026, 9, 1)] == Decimal("1")
                assert result.undersupply[part.id][date(2026, 9, 1)] == Decimal("0")

                allocations = (
                    await session.execute(
                        select(InventoryPlanAllocation)
                        .where(InventoryPlanAllocation.inventory_item_id == item.id)
                        .order_by(InventoryPlanAllocation.plan_id)
                    )
                ).scalars().all()
                assert [(row.plan_id, row.qty_covered) for row in allocations] == [
                    (august.id, Decimal("6")),
                    (september.id, Decimal("5")),
                ]

                august_coverage = await _plan_parts_with_coverage(
                    august.id, session, plan_part_id=august_row.id
                )
                assert august_coverage[0]["qty_inventory_covered_total"] == "6.000000"
                assert august_coverage[0]["qty_invoice_covered_total"] == "4.000000"
                assert august_coverage[0]["qty_covered_total"] == "10.000000"
                assert august_coverage[0]["delivery_complete"] is True

                try:
                    await update_plan_part(
                        august.id,
                        august_row.id,
                        MonthlyPlanPartUpdate(qty_delivered=Decimal("5")),
                        session,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 400
                else:
                    raise AssertionError("Inventory-covered quantity must reduce manual delivery maximum")

                updated_row = await update_plan_part(
                    august.id,
                    august_row.id,
                    MonthlyPlanPartUpdate(qty_delivered=Decimal("4")),
                    session,
                )
                assert updated_row.qty_delivered == Decimal("4")

                remainders = await get_remainders(session)
                assert remainders["current_month"] == "2026-09-01"
                assert remainders["remainders"] == [
                    {
                        "part_id": part.id,
                        "name": part.name,
                        "part_type": None,
                        "remainder": "1.000000",
                        "invoice_remainder": "0",
                        "inventory_remainder": "1.000000",
                        "overorders": {},
                        "inventory_additions": {"2026-08-01": "12.000000"},
                        "inventory_consumed": {
                            "2026-08-01": "6.000000",
                            "2026-09-01": "5.000000",
                        },
                    }
                ]

                # Повторный пересчёт удаляет производные строки и создаёт их заново,
                # а не добавляет второй комплект поверх первого.
                await recompute_carryover_links(session)
                allocation_count = await session.scalar(
                    select(func.count()).select_from(InventoryPlanAllocation)
                )
                carryover_count = await session.scalar(
                    select(func.count())
                    .select_from(InvoicePartLink)
                    .where(InvoicePartLink.is_carryover.is_(True))
                )
                assert allocation_count == 2
                assert carryover_count == 0

                # Отмена документа полностью исключает его из текущего и будущих
                # месяцев, сохраняя сам документ и строки для аудита.
                document.status = "cancelled"
                await session.flush()
                await recompute_carryover_links(session)
                cancelled_result = await compute_carryover(session)
                assert await session.scalar(
                    select(func.count()).select_from(InventoryPlanAllocation)
                ) == 0
                assert cancelled_result.undersupply[part.id][date(2026, 8, 1)] == Decimal("6")
                assert cancelled_result.undersupply[part.id][date(2026, 9, 1)] == Decimal("5")
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_saving_same_month_replaces_inventory_instead_of_adding_a_duplicate():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                part = Part(name="Одна деталь")
                plan = MonthlyPlan(month=date(2026, 10, 1), revision=1)
                session.add_all([part, plan])
                await session.flush()
                session.add(
                    MonthlyPlanPart(
                        plan_id=plan.id,
                        part_id=part.id,
                        qty_required=Decimal("3"),
                        qty_final=Decimal("3"),
                        qty_delivered=Decimal("0"),
                    )
                )
                await session.flush()

                request = Request(
                    {
                        "type": "http",
                        "method": "POST",
                        "path": "/monthly-plans/inventory/2026-10-01",
                        "headers": [],
                    }
                )

                first = await save_inventory_document(
                    date(2026, 10, 1),
                    InventoryDocumentUpsert(
                        items=[InventoryItemUpsert(part_id=part.id, qty_found=Decimal("5"))]
                    ),
                    request,
                    session,
                )
                assert first.items[0].qty_found == Decimal("5")

                second = await save_inventory_document(
                    date(2026, 10, 1),
                    InventoryDocumentUpsert(
                        items=[InventoryItemUpsert(part_id=part.id, qty_found=Decimal("7"))]
                    ),
                    request,
                    session,
                )
                assert len(second.items) == 1
                assert second.items[0].qty_found == Decimal("7")
                assert await session.scalar(
                    select(func.count()).select_from(InventoryDocument)
                ) == 1
                assert await session.scalar(
                    select(func.count()).select_from(InventoryItem)
                ) == 1
                assert await session.scalar(
                    select(func.count()).select_from(InventoryPlanAllocation)
                ) == 1

                result = await compute_carryover(session)
                assert result.balances[part.id][date(2026, 10, 1)] == Decimal("4")

                cancelled = await cancel_inventory_document(
                    date(2026, 10, 1), request, session
                )
                assert cancelled.status == "cancelled"
                assert await session.scalar(
                    select(func.count()).select_from(InventoryPlanAllocation)
                ) == 0
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_last_plan_with_posted_inventory_cannot_be_deleted():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                part = Part(name="Деталь защищённого месяца")
                plan = MonthlyPlan(month=date(2026, 11, 1), revision=1)
                session.add_all([part, plan])
                await session.flush()
                document = InventoryDocument(month=plan.month, status="posted")
                session.add(document)
                await session.flush()
                session.add(
                    InventoryItem(
                        inventory_id=document.id,
                        part_id=part.id,
                        qty_found=Decimal("2"),
                    )
                )
                await session.flush()

                try:
                    await delete_monthly_plan(plan.id, session)
                except HTTPException as exc:
                    assert exc.status_code == 409
                    assert "Сначала отмените инвентаризацию" in exc.detail
                else:  # pragma: no cover
                    raise AssertionError("План с проведённой инвентаризацией был удалён")

                assert await session.get(MonthlyPlan, plan.id) is not None
        finally:
            await engine.dispose()

    asyncio.run(run())
