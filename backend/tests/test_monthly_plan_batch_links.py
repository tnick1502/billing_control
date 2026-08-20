import asyncio
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.monthly_plans import create_plan_invoice_links_batch, delete_plan_invoice_link
from app.database import Base
from app.models import Invoice, InvoicePartLink, MonthlyPlan, MonthlyPlanPart, Part
from app.schemas.common import (
    InvoicePartLinkRead,
    MonthlyPlanInvoiceLinkBatchCreate,
    MonthlyPlanInvoiceLinkBatchItem,
)


def test_batch_invoice_linking_is_atomic_and_uses_plan_rows():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                parts = [Part(name="Деталь 1"), Part(name="Деталь 2")]
                plan = MonthlyPlan(month=date(2026, 8, 1), revision=1)
                invoice = Invoice(invoice_no="СФ-8", invoice_date=date(2026, 8, 10))
                session.add_all([*parts, plan, invoice])
                await session.flush()

                plan_rows = [
                    MonthlyPlanPart(
                        plan_id=plan.id,
                        part_id=part.id,
                        qty_required=Decimal("10"),
                        qty_final=Decimal("10"),
                        qty_delivered=Decimal("0"),
                    )
                    for part in parts
                ]
                session.add_all(plan_rows)
                await session.flush()

                payload = MonthlyPlanInvoiceLinkBatchCreate(
                    invoice_id=invoice.id,
                    items=[
                        MonthlyPlanInvoiceLinkBatchItem(
                            plan_part_id=plan_rows[0].id,
                            qty_covered=Decimal("4"),
                        ),
                        MonthlyPlanInvoiceLinkBatchItem(
                            plan_part_id=plan_rows[1].id,
                            qty_covered=Decimal("7"),
                        ),
                    ],
                )
                links = await create_plan_invoice_links_batch(plan.id, payload, session)

                assert [(link.part_id, link.qty_covered) for link in links] == [
                    (parts[0].id, Decimal("4")),
                    (parts[1].id, Decimal("7")),
                ]
                # Поля, включая серверные id/created_at, готовы к ответу API сразу после flush.
                assert all(InvoicePartLinkRead.model_validate(link) for link in links)

                # Повторная массовая операция целиком отклоняется: новых строк не появляется.
                try:
                    await create_plan_invoice_links_batch(plan.id, payload, session)
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    raise AssertionError("Duplicate batch must be rejected")

                count = await session.scalar(select(func.count()).select_from(InvoicePartLink))
                assert count == 2

                await delete_plan_invoice_link(plan.id, links[0].id, session)
                remaining = await session.scalar(select(func.count()).select_from(InvoicePartLink))
                assert remaining == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_batch_rejects_rows_from_another_plan_before_writing_any_links():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                part = Part(name="Деталь")
                plan = MonthlyPlan(month=date(2026, 8, 1), revision=1)
                other_plan = MonthlyPlan(month=date(2026, 9, 1), revision=1)
                invoice = Invoice(invoice_no="СФ-9", invoice_date=date(2026, 8, 11))
                session.add_all([part, plan, other_plan, invoice])
                await session.flush()
                other_row = MonthlyPlanPart(
                    plan_id=other_plan.id,
                    part_id=part.id,
                    qty_required=Decimal("3"),
                    qty_final=Decimal("3"),
                    qty_delivered=Decimal("0"),
                )
                session.add(other_row)
                await session.flush()

                payload = MonthlyPlanInvoiceLinkBatchCreate(
                    invoice_id=invoice.id,
                    items=[
                        MonthlyPlanInvoiceLinkBatchItem(
                            plan_part_id=other_row.id,
                            qty_covered=Decimal("3"),
                        )
                    ],
                )
                try:
                    await create_plan_invoice_links_batch(plan.id, payload, session)
                except HTTPException as exc:
                    assert exc.status_code == 400
                else:
                    raise AssertionError("Foreign plan row must be rejected")

                count = await session.scalar(select(func.count()).select_from(InvoicePartLink))
                assert count == 0
        finally:
            await engine.dispose()

    asyncio.run(run())
