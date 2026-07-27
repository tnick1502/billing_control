import asyncio
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.monthly_plans import _plan_parts_with_coverage
from app.database import Base
from app.models import Invoice, InvoicePartLink, MonthlyPlan, MonthlyPlanPart


def test_coverage_can_be_loaded_for_only_requested_plan_rows():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                plan = MonthlyPlan(month=date(2026, 7, 1), revision=1)
                session.add(plan)
                await session.flush()

                rows = [
                    MonthlyPlanPart(
                        plan_id=plan.id,
                        part_id=part_id,
                        qty_required=Decimal("5"),
                        qty_final=Decimal("5"),
                        qty_delivered=Decimal(str(delivered)),
                    )
                    for part_id, delivered in ((101, 2), (102, 5))
                ]
                session.add_all(rows)
                await session.flush()

                invoice = Invoice(
                    invoice_no="СФ-2026-07",
                    invoice_date=date(2026, 7, 21),
                    supplier="ООО Поставщик",
                )
                session.add(invoice)
                await session.flush()
                session.add(
                    InvoicePartLink(
                        invoice_id=invoice.id,
                        plan_id=plan.id,
                        part_id=rows[0].part_id,
                        qty_covered=Decimal("3"),
                        is_carryover=False,
                    )
                )
                await session.flush()

                one = await _plan_parts_with_coverage(
                    plan.id,
                    session,
                    plan_part_id=rows[0].id,
                )
                assert [item["id"] for item in one] == [rows[0].id]
                assert one[0]["qty_covered_total"] == "3.000000"
                assert one[0]["invoices"][0]["invoice_date"] == "2026-07-21"
                assert one[0]["delivery_complete"] is False

                batch = await _plan_parts_with_coverage(
                    plan.id,
                    session,
                    plan_part_ids=[rows[1].id],
                )
                assert [item["id"] for item in batch] == [rows[1].id]
                assert batch[0]["delivery_complete"] is True

                try:
                    await _plan_parts_with_coverage(
                        plan.id,
                        session,
                        plan_part_id=999_999,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 404
                else:
                    raise AssertionError("A missing plan row must return HTTP 404")
        finally:
            await engine.dispose()

    asyncio.run(run())
