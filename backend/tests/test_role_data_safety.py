"""Проверки границ прав на данных в изолированной SQLite БД."""

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.files import download_file
from app.api.auth import _copy_role_name
from app.database import Base
from app.models import (
    Device,
    DeviceBomVersion,
    File,
    FileContent,
    Invoice,
    InvoiceFile,
    MonthlyPlan,
    MonthlyPlanPart,
    MonthlyPlanPartFile,
    Part,
)
from app.permissions import build_policy
from app.tools.bulk_import import (
    BomItemSpec,
    BomSpec,
    DeviceSpec,
    ImportAuthorizationError,
    ImportDoc,
    PartSpec,
    import_document,
)


def _request(permissions: dict[str, str]) -> Request:
    request = Request({"type": "http", "method": "GET", "path": "/files/1/download", "headers": []})
    request.state.policy = build_policy("limited", permissions, False)
    return request


def test_copy_name_keeps_suffix_with_max_length_source():
    source = "Р" * 128
    first = _copy_role_name(source, 1)
    second = _copy_role_name(source, 2)
    assert len(first) == len(second) == 128
    assert first != source and first.endswith(" (копия)")
    assert second != first and second.endswith(" (копия 2)")


def test_file_download_requires_permission_for_its_actual_link():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with maker() as session:
                invoice = Invoice(invoice_no="I-1", invoice_date=date(2026, 1, 1))
                plan = MonthlyPlan(month=date(2026, 1, 1), revision=1, status="draft")
                part = Part(name="Деталь")
                invoice_file = File(filename="invoice.txt", content=FileContent(data=b"invoice"))
                plan_file = File(filename="plan.txt", content=FileContent(data=b"plan"))
                session.add_all([invoice, plan, part, invoice_file, plan_file])
                await session.flush()
                plan_part = MonthlyPlanPart(
                    plan_id=plan.id, part_id=part.id,
                    qty_required=Decimal("1"), qty_final=Decimal("1"), qty_delivered=Decimal("0"),
                )
                session.add(plan_part)
                await session.flush()
                session.add_all([
                    InvoiceFile(invoice_id=invoice.id, file_id=invoice_file.id),
                    MonthlyPlanPartFile(plan_part_id=plan_part.id, file_id=plan_file.id),
                ])
                await session.commit()

                invoices_only = _request({"invoices": "view"})
                plans_only = _request({"monthly_plans": "view"})
                assert (await download_file(invoice_file.id, invoices_only, session)).body == b"invoice"
                assert (await download_file(plan_file.id, plans_only, session)).body == b"plan"
                with pytest.raises(HTTPException) as denied_plan:
                    await download_file(plan_file.id, invoices_only, session)
                with pytest.raises(HTTPException) as denied_invoice:
                    await download_file(invoice_file.id, plans_only, session)
                assert denied_plan.value.status_code == denied_invoice.value.status_code == 404
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_import_edit_cannot_archive_existing_active_bom():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with maker() as session:
                device = Device(primary_name="Device")
                session.add(device)
                await session.flush()
                current = DeviceBomVersion(device_id=device.id, version=1, status="active")
                session.add(current)
                await session.commit()

                def doc(status: str, version: int) -> ImportDoc:
                    return ImportDoc(devices=[DeviceSpec(
                        path="devices[0]", primary_name="Device",
                        bom=BomSpec(
                            name=None, description=None, version=version, status=status,
                            items=[BomItemSpec(
                                path="devices[0].bom.items[0]", qty_per_device=1,
                                part=PartSpec(name="Part"),
                            )],
                        ),
                    )])

                with pytest.raises(ImportAuthorizationError, match="уровень «Полный»"):
                    await import_document(
                        session, doc("active", 2), update_existing=False,
                        allow_destructive=False,
                    )
                await session.rollback()
                statuses = (await session.execute(
                    select(DeviceBomVersion.version, DeviceBomVersion.status).order_by(DeviceBomVersion.version)
                )).all()
                assert statuses == [(1, "active")]

                with pytest.raises(ImportAuthorizationError, match="пересборка"):
                    await import_document(
                        session, doc("active", 1), update_existing=True,
                        allow_destructive=False,
                    )
                await session.rollback()
                statuses = (await session.execute(
                    select(DeviceBomVersion.version, DeviceBomVersion.status).order_by(DeviceBomVersion.version)
                )).all()
                assert statuses == [(1, "active")]

                await import_document(
                    session, doc("draft", 2), update_existing=False,
                    allow_destructive=False,
                )
                await session.commit()
                statuses = (await session.execute(
                    select(DeviceBomVersion.version, DeviceBomVersion.status).order_by(DeviceBomVersion.version)
                )).all()
                assert statuses == [(1, "active"), (2, "draft")]

                await import_document(
                    session, doc("active", 3), update_existing=False,
                    allow_destructive=True,
                )
                await session.commit()
                statuses = (await session.execute(
                    select(DeviceBomVersion.version, DeviceBomVersion.status).order_by(DeviceBomVersion.version)
                )).all()
                assert statuses == [(1, "archived"), (2, "draft"), (3, "active")]
        finally:
            await engine.dispose()

    asyncio.run(run())
