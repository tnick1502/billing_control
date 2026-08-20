from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Device,
    DeviceBomVersion,
    MonthlyPlan,
    MonthlyPlanDevice,
    MonthlyPlanPart,
    InvoicePartLink,
    Invoice,
    InventoryDocument,
    InventoryItem,
    InventoryPlanAllocation,
    Part,
)
from app.models.monthly_plan import MonthlyPlanPartFile
from app.models.invoice import File as FileModel
from app.schemas.common import (
    FileRead,
    MonthlyPlanCreate,
    MonthlyPlanRead,
    MonthlyPlanUpdate,
    MonthlyPlanGenerate,
    InventoryDocumentRead,
    InventoryDocumentUpsert,
    MonthlyPlanDeviceRead,
    MonthlyPlanInvoiceLinkBatchCreate,
    MonthlyPlanPartRead,
    MonthlyPlanPartUpdate,
    InvoicePartLinkRead,
)
from app.services.carryover import acquire_carryover_lock, compute_carryover, recompute_carryover_links
from app.services.file_storage import delete_orphaned_files, save_upload_as_file
from app.services.monthly_plan import generate_monthly_plan as do_generate
from app.services.monthly_plan_excel import (
    PlanDeviceExportRow,
    PlanExportMeta,
    PlanInvoiceExportRow,
    PlanPartExportRow,
    build_monthly_plan_xlsx,
)

router = APIRouter(prefix="/monthly-plans", tags=["monthly-plans"])


@router.get("", response_model=list[MonthlyPlanRead])
async def list_monthly_plans(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(MonthlyPlan).order_by(MonthlyPlan.month.desc(), MonthlyPlan.revision.desc())
    )
    return result.scalars().all()


@router.post("", response_model=MonthlyPlanRead)
async def create_monthly_plan(data: MonthlyPlanCreate, session: AsyncSession = Depends(get_db)):
    plan = MonthlyPlan(**data.model_dump())
    session.add(plan)
    await session.flush()
    await session.refresh(plan)
    return plan


@router.post("/generate", response_model=MonthlyPlanRead)
async def generate_plan(data: MonthlyPlanGenerate, session: AsyncSession = Depends(get_db)):
    try:
        plan = await do_generate(session, data.month, data.replace)
        await session.flush()
        await recompute_carryover_links(session)
        await session.refresh(plan)
        return plan
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/remainders")
async def get_remainders(session: AsyncSession = Depends(get_db)):
    """Общие остатки деталей на последний рассчитанный план + недозаказ текущего месяца.

    - remainders: фактический расчётный остаток на конец последнего месяца с разбивкой
      на излишки счетов и физически найденное при инвентаризации.
    - undersupply: потребность, не закрытая остатками, инвентаризацией и счетами.

    Объявлен ВЫШЕ /{plan_id}, иначе FastAPI примет "remainders" за plan_id.
    """
    result = await compute_carryover(session)
    if not result.months:
        return {"current_month": None, "remainders": [], "undersupply": []}

    current = result.months[-1]
    remainders = []
    undersupply = []
    for part_id, meta in result.parts.items():
        balances = result.balances.get(part_id, {})
        overorders = result.overorders.get(part_id, {})
        inventory_additions = result.inventory_additions.get(part_id, {})
        inventory_consumed = result.inventory_consumed.get(part_id, {})
        invoice_balances = result.invoice_balances.get(part_id, {})
        inventory_balances = result.inventory_balances.get(part_id, {})
        under = result.undersupply.get(part_id, {})

        remainder = balances.get(current, Decimal("0"))
        if remainder > 0:
            remainders.append(
                {
                    "part_id": part_id,
                    "name": meta["name"],
                    "part_type": meta["part_type"],
                    "remainder": str(remainder),
                    "invoice_remainder": str(invoice_balances.get(current, Decimal("0"))),
                    "inventory_remainder": str(inventory_balances.get(current, Decimal("0"))),
                    "overorders": {
                        m.isoformat(): str(v) for m, v in sorted(overorders.items()) if v > 0
                    },
                    "inventory_additions": {
                        m.isoformat(): str(v)
                        for m, v in sorted(inventory_additions.items())
                        if v > 0
                    },
                    "inventory_consumed": {
                        m.isoformat(): str(v)
                        for m, v in sorted(inventory_consumed.items())
                        if v > 0
                    },
                }
            )

        under_cur = under.get(current, Decimal("0"))
        if under_cur > 0:
            undersupply.append(
                {
                    "part_id": part_id,
                    "name": meta["name"],
                    "part_type": meta["part_type"],
                    "qty": str(under_cur),
                }
            )

    remainders.sort(key=lambda p: (p["name"] or "").lower())
    undersupply.sort(key=lambda p: (p["name"] or "").lower())
    return {"current_month": current.isoformat(), "remainders": remainders, "undersupply": undersupply}


def _validate_inventory_month(month: date) -> None:
    if month.day != 1:
        raise HTTPException(400, "Месяц инвентаризации должен быть первым числом месяца")


async def _inventory_document_payload(
    session: AsyncSession,
    month: date,
) -> InventoryDocument | None:
    return await session.scalar(
        select(InventoryDocument)
        .options(selectinload(InventoryDocument.items))
        .where(InventoryDocument.month == month)
        .execution_options(populate_existing=True)
    )


@router.get("/inventory/{month}", response_model=InventoryDocumentRead | None)
async def get_inventory_document(month: date, session: AsyncSession = Depends(get_db)):
    """Вернуть инвентаризацию календарного месяца, включая отменённую."""
    _validate_inventory_month(month)
    return await _inventory_document_payload(session, month)


@router.post("/inventory/{month}", response_model=InventoryDocumentRead)
async def save_inventory_document(
    month: date,
    data: InventoryDocumentUpsert,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Атомарно провести или полностью заменить инвентаризацию месяца.

    Замена, а не добавление поверх старых строк, делает повторное сохранение
    идемпотентным на уровне бизнес-данных и исключает двойной учёт.
    """
    _validate_inventory_month(month)
    await acquire_carryover_lock(session)

    plan_exists = await session.scalar(
        select(MonthlyPlan.id).where(MonthlyPlan.month == month).limit(1)
    )
    if plan_exists is None:
        raise HTTPException(409, "Сначала создайте месячный план за выбранный месяц")

    requested_part_ids = [item.part_id for item in data.items]
    existing_part_ids = set(
        (
            await session.execute(
                select(Part.id).where(Part.id.in_(requested_part_ids))
            )
        ).scalars().all()
    )
    missing = [part_id for part_id in requested_part_ids if part_id not in existing_part_ids]
    if missing:
        raise HTTPException(400, "Не найдены детали с ID: " + ", ".join(map(str, missing)))

    document = await session.scalar(
        select(InventoryDocument)
        .where(InventoryDocument.month == month)
        .with_for_update()
    )
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    now = datetime.now(timezone.utc)
    if document is None:
        document = InventoryDocument(
            month=month,
            status="posted",
            note=(data.note or "").strip() or None,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
            updated_at=now,
        )
        session.add(document)
        await session.flush()
    else:
        document.status = "posted"
        document.note = (data.note or "").strip() or None
        document.updated_by_user_id = user_id
        document.updated_at = now
        await session.execute(
            delete(InventoryItem).where(InventoryItem.inventory_id == document.id)
        )
        await session.flush()

    session.add_all(
        [
            InventoryItem(
                inventory_id=document.id,
                part_id=item.part_id,
                qty_found=item.qty_found,
                note=(item.note or "").strip() or None,
                updated_at=now,
            )
            for item in data.items
        ]
    )
    await session.flush()
    await recompute_carryover_links(session)
    payload = await _inventory_document_payload(session, month)
    if payload is None:  # pragma: no cover — защищает контракт ответа при сбое ORM
        raise HTTPException(500, "Не удалось перечитать сохранённую инвентаризацию")
    return payload


@router.delete("/inventory/{month}", response_model=InventoryDocumentRead)
async def cancel_inventory_document(
    month: date,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Отменить влияние документа, сохранив его строки для аудита и восстановления."""
    _validate_inventory_month(month)
    await acquire_carryover_lock(session)
    document = await session.scalar(
        select(InventoryDocument)
        .where(InventoryDocument.month == month)
        .with_for_update()
    )
    if document is None:
        raise HTTPException(404, "Инвентаризация за выбранный месяц не найдена")
    document.status = "cancelled"
    document.updated_by_user_id = getattr(getattr(request.state, "user", None), "id", None)
    document.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await recompute_carryover_links(session)
    payload = await _inventory_document_payload(session, month)
    if payload is None:  # pragma: no cover
        raise HTTPException(500, "Не удалось перечитать отменённую инвентаризацию")
    return payload


@router.get("/{plan_id}", response_model=MonthlyPlanRead)
async def get_monthly_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(MonthlyPlan).where(MonthlyPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Monthly plan not found")
    return plan


@router.get("/{plan_id}/export.xlsx")
async def export_monthly_plan_excel(plan_id: int, session: AsyncSession = Depends(get_db)):
    """Скачать месячный план в Excel с группировкой, шифрами и состоянием исполнения."""
    plan = await session.get(MonthlyPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Monthly plan not found")

    device_result = await session.execute(
        select(MonthlyPlanDevice, Device, DeviceBomVersion)
        .join(Device, Device.id == MonthlyPlanDevice.device_id)
        .join(DeviceBomVersion, DeviceBomVersion.id == MonthlyPlanDevice.bom_version_id)
        .where(MonthlyPlanDevice.plan_id == plan_id)
    )
    devices = [
        PlanDeviceExportRow(
            device_id=row.device_id,
            name=device.primary_name,
            model=device.model,
            qty_total=row.qty_total,
            bom_version=bom.version,
            bom_name=bom.name,
            bom_status=bom.status,
        )
        for row, device, bom in device_result.all()
    ]

    coverage_result = await session.execute(
        select(InvoicePartLink.part_id, func.coalesce(func.sum(InvoicePartLink.qty_covered), 0))
        .where(InvoicePartLink.plan_id == plan_id)
        .group_by(InvoicePartLink.part_id)
    )
    coverage_by_part = {part_id: qty for part_id, qty in coverage_result.all()}
    inventory_coverage_result = await session.execute(
        select(
            InventoryPlanAllocation.part_id,
            func.coalesce(func.sum(InventoryPlanAllocation.qty_covered), 0),
        )
        .where(InventoryPlanAllocation.plan_id == plan_id)
        .group_by(InventoryPlanAllocation.part_id)
    )
    inventory_coverage_by_part = {
        part_id: qty for part_id, qty in inventory_coverage_result.all()
    }

    part_result = await session.execute(
        select(MonthlyPlanPart, Part)
        .join(Part, Part.id == MonthlyPlanPart.part_id)
        .where(MonthlyPlanPart.plan_id == plan_id)
    )
    parts = [
        PlanPartExportRow(
            part_id=row.part_id,
            name=part.name,
            cipher=part.cipher,
            article=part.article,
            part_type=part.part_type,
            qty_required=row.qty_required,
            qty_final=row.qty_final,
            qty_covered=(
                coverage_by_part.get(row.part_id, Decimal("0"))
                + inventory_coverage_by_part.get(row.part_id, Decimal("0"))
            ),
            qty_delivered=min(
                row.qty_final,
                row.qty_delivered
                + inventory_coverage_by_part.get(row.part_id, Decimal("0")),
            ),
        )
        for row, part in part_result.all()
    ]

    invoice_result = await session.execute(
        select(InvoicePartLink, Invoice, Part)
        .join(Invoice, Invoice.id == InvoicePartLink.invoice_id)
        .join(Part, Part.id == InvoicePartLink.part_id)
        .where(InvoicePartLink.plan_id == plan_id)
    )
    invoices = [
        PlanInvoiceExportRow(
            part_id=link.part_id,
            part_name=part.name,
            cipher=part.cipher,
            part_type=part.part_type,
            invoice_no=invoice.invoice_no,
            invoice_date=invoice.invoice_date,
            supplier=invoice.supplier,
            qty_covered=link.qty_covered or Decimal("0"),
            payment_date=invoice.payment_date,
            is_carryover=link.is_carryover,
        )
        for link, invoice, part in invoice_result.all()
    ]

    payload = build_monthly_plan_xlsx(
        PlanExportMeta(
            id=plan.id,
            month=plan.month,
            revision=plan.revision,
            status=plan.status,
            generated_at=plan.generated_at,
            generated_by=plan.generated_by,
            note=plan.note,
        ),
        devices,
        parts,
        invoices,
    )
    filename = f"monthly_plan_{plan.month:%Y-%m}.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{plan_id}", response_model=MonthlyPlanRead)
async def update_monthly_plan(plan_id: int, data: MonthlyPlanUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(MonthlyPlan).where(MonthlyPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Monthly plan not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(plan, k, v)
    await session.flush()
    await session.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_monthly_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    await acquire_carryover_lock(session)
    result = await session.execute(select(MonthlyPlan).where(MonthlyPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Monthly plan not found")
    plans_in_month = await session.scalar(
        select(func.count()).where(MonthlyPlan.month == plan.month)
    )
    if plans_in_month == 1:
        posted_inventory = await session.scalar(
            select(func.count()).where(
                InventoryDocument.month == plan.month,
                InventoryDocument.status == "posted",
            )
        )
        if posted_inventory:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Нельзя удалить последний план месяца: за этот месяц проведена "
                    "инвентаризация. Сначала отмените инвентаризацию."
                ),
            )
    link_count = await session.scalar(
        select(func.count()).where(
            InvoicePartLink.plan_id == plan_id,
            InvoicePartLink.is_carryover.is_(False),
        )
    )
    if link_count:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить план: к нему привязано {link_count} счетов. Удалите привязки счётов перед удалением плана.",
        )
    await session.delete(plan)
    await session.flush()
    await recompute_carryover_links(session)
    return None


@router.get("/{plan_id}/devices", response_model=list[MonthlyPlanDeviceRead])
async def list_plan_devices(plan_id: int, session: AsyncSession = Depends(get_db)):
    if not await session.get(MonthlyPlan, plan_id):
        raise HTTPException(404, "Monthly plan not found")
    result = await session.execute(select(MonthlyPlanDevice).where(MonthlyPlanDevice.plan_id == plan_id))
    return result.scalars().all()


@router.get("/{plan_id}/parts", response_model=list[MonthlyPlanPartRead])
async def list_plan_parts(plan_id: int, session: AsyncSession = Depends(get_db)):
    if not await session.get(MonthlyPlan, plan_id):
        raise HTTPException(404, "Monthly plan not found")
    result = await session.execute(select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id == plan_id))
    return result.scalars().all()


@router.post("/{plan_id}/invoice-links/batch", response_model=list[InvoicePartLinkRead])
async def create_plan_invoice_links_batch(
    plan_id: int,
    data: MonthlyPlanInvoiceLinkBatchCreate,
    session: AsyncSession = Depends(get_db),
):
    """Атомарно привязать один счёт к нескольким выбранным строкам плана."""
    # Сериализуемся с пересчётом переносов и другими массовыми привязками. Блокировка
    # транзакционная и на SQLite является no-op.
    await acquire_carryover_lock(session)

    if not await session.get(MonthlyPlan, plan_id):
        raise HTTPException(404, "Monthly plan not found")
    if not await session.get(Invoice, data.invoice_id):
        raise HTTPException(404, "Счёт не найден")

    requested_ids = [item.plan_part_id for item in data.items]
    rows_result = await session.execute(
        select(MonthlyPlanPart).where(
            MonthlyPlanPart.plan_id == plan_id,
            MonthlyPlanPart.id.in_(requested_ids),
        )
    )
    rows = list(rows_result.scalars().all())
    rows_by_id = {row.id: row for row in rows}
    missing_ids = [row_id for row_id in requested_ids if row_id not in rows_by_id]
    if missing_ids:
        raise HTTPException(
            400,
            f"Строки не принадлежат выбранному месячному плану: {', '.join(map(str, missing_ids))}",
        )

    part_ids = [rows_by_id[row_id].part_id for row_id in requested_ids]
    existing_result = await session.execute(
        select(InvoicePartLink.part_id).where(
            InvoicePartLink.invoice_id == data.invoice_id,
            InvoicePartLink.plan_id == plan_id,
            InvoicePartLink.part_id.in_(part_ids),
        )
    )
    existing_part_ids = set(existing_result.scalars().all())
    if existing_part_ids:
        raise HTTPException(
            409,
            "Счёт уже привязан к выбранным деталям с ID: "
            + ", ".join(map(str, sorted(existing_part_ids))),
        )

    links = [
        InvoicePartLink(
            invoice_id=data.invoice_id,
            plan_id=plan_id,
            part_id=rows_by_id[item.plan_part_id].part_id,
            qty_covered=item.qty_covered,
            note=item.note,
            is_carryover=False,
        )
        for item in data.items
    ]
    session.add_all(links)
    await session.flush()
    await recompute_carryover_links(session)
    return links


@router.delete("/{plan_id}/invoice-links/{link_id}", status_code=204)
async def delete_plan_invoice_link(
    plan_id: int,
    link_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Отвязать ручную привязку из месячного плана, не открывая удаление счетов сотруднику."""
    await acquire_carryover_lock(session)
    link = await session.scalar(
        select(InvoicePartLink).where(
            InvoicePartLink.id == link_id,
            InvoicePartLink.plan_id == plan_id,
        )
    )
    if not link:
        raise HTTPException(404, "Привязка счёта не найдена")
    if link.is_carryover:
        raise HTTPException(400, "Привязка-перенос пересобирается автоматически и не отвязывается вручную")
    await session.delete(link)
    await session.flush()
    await recompute_carryover_links(session)
    return None


@router.patch("/{plan_id}/parts/{plan_part_id}", response_model=MonthlyPlanPartRead)
async def update_plan_part(
    plan_id: int,
    plan_part_id: int,
    data: MonthlyPlanPartUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Ручная корректировка строки плана (админ или сотрудник с доступом к плану).

    - ``qty_final`` — итоговая потребность к закупке (по умолчанию = расчётной qty_required).
      Изменение влияет на покрытие, переносы остатков и допустимый максимум «поставлено».
    - ``qty_delivered`` — фактически поставлено по поставкам; физически найденное
      количество учитывается отдельно и уменьшает доступный максимум ручного ввода.
    """
    result = await session.execute(
        select(MonthlyPlanPart).where(
            MonthlyPlanPart.id == plan_part_id,
            MonthlyPlanPart.plan_id == plan_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Строка плана не найдена")

    final_changed = False
    if data.qty_final is not None:
        row.qty_final = data.qty_final
        final_changed = True
        # «Поставлено» не может превышать новую итоговую потребность.
        if row.qty_delivered > row.qty_final:
            row.qty_delivered = row.qty_final

    await session.flush()
    # Изменение итоговой потребности меняет распределение обоих источников остатков.
    if final_changed:
        await recompute_carryover_links(session)

    if data.qty_delivered is not None:
        inventory_covered = await session.scalar(
            select(func.coalesce(func.sum(InventoryPlanAllocation.qty_covered), 0)).where(
                InventoryPlanAllocation.plan_id == plan_id,
                InventoryPlanAllocation.part_id == row.part_id,
            )
        )
        max_manual_delivery = max(row.qty_final - Decimal(inventory_covered or 0), Decimal("0"))
        if data.qty_delivered > max_manual_delivery:
            raise HTTPException(
                400,
                "Поставлено по поставкам не должно превышать потребность за вычетом инвентаризации",
            )
        row.qty_delivered = data.qty_delivered

    await session.flush()
    await session.refresh(row)
    return row


@router.get("/{plan_id}/parts/{plan_part_id}/files", response_model=list[FileRead])
async def list_plan_part_files(plan_id: int, plan_part_id: int, session: AsyncSession = Depends(get_db)):
    row = await session.scalar(
        select(MonthlyPlanPart).where(
            MonthlyPlanPart.id == plan_part_id,
            MonthlyPlanPart.plan_id == plan_id,
        )
    )
    if not row:
        raise HTTPException(404, "Строка плана не найдена")
    result = await session.execute(
        select(FileModel)
        .join(MonthlyPlanPartFile, MonthlyPlanPartFile.file_id == FileModel.id)
        .where(MonthlyPlanPartFile.plan_part_id == plan_part_id)
        .order_by(MonthlyPlanPartFile.created_at)
    )
    return result.scalars().all()


@router.post("/{plan_id}/parts/{plan_part_id}/files", response_model=list[FileRead])
async def upload_plan_part_files(
    plan_id: int,
    plan_part_id: int,
    files: List[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db),
):
    row = await session.scalar(
        select(MonthlyPlanPart).where(
            MonthlyPlanPart.id == plan_part_id,
            MonthlyPlanPart.plan_id == plan_id,
        )
    )
    if not row:
        raise HTTPException(404, "Строка плана не найдена")
    if not files:
        raise HTTPException(400, "Файлы не переданы")
    saved: list[FileModel] = []
    for upload in files:
        try:
            f = await save_upload_as_file(session, upload)
        except ValueError as e:
            raise HTTPException(400, str(e))
        link = MonthlyPlanPartFile(plan_part_id=plan_part_id, file_id=f.id)
        session.add(link)
        saved.append(f)
    await session.flush()
    return saved


@router.delete("/{plan_id}/parts/{plan_part_id}/files/{file_id}", status_code=204)
async def delete_plan_part_file(
    plan_id: int,
    plan_part_id: int,
    file_id: int,
    session: AsyncSession = Depends(get_db),
):
    link = await session.scalar(
        select(MonthlyPlanPartFile).where(
            MonthlyPlanPartFile.plan_part_id == plan_part_id,
            MonthlyPlanPartFile.file_id == file_id,
        )
    )
    if not link:
        raise HTTPException(404, "Файл не найден")
    await session.delete(link)
    await session.flush()
    await delete_orphaned_files(session, [file_id])
    return None


async def _plan_parts_with_coverage(
    plan_id: int,
    session: AsyncSession,
    *,
    plan_part_id: int | None = None,
    plan_part_ids: list[int] | None = None,
) -> list[dict]:
    """Build coverage data for a whole plan or one requested plan row."""
    if not await session.get(MonthlyPlan, plan_id):
        raise HTTPException(404, "Monthly plan not found")
    parts_query = select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id == plan_id)
    if plan_part_id is not None:
        parts_query = parts_query.where(MonthlyPlanPart.id == plan_part_id)
    elif plan_part_ids is not None:
        parts_query = parts_query.where(MonthlyPlanPart.id.in_(plan_part_ids))
    parts_result = await session.execute(parts_query)
    parts = list(parts_result.scalars().all())
    if plan_part_id is not None and not parts:
        raise HTTPException(404, "Строка плана не найдена")

    part_ids = [p.part_id for p in parts]
    links_result = await session.execute(
        select(
            InvoicePartLink.id.label("link_id"),
            InvoicePartLink.part_id,
            InvoicePartLink.invoice_id,
            Invoice.invoice_no,
            Invoice.invoice_date,
            Invoice.supplier,
            Invoice.payment_date,
            InvoicePartLink.qty_covered,
            InvoicePartLink.is_carryover,
        )
        .join(Invoice, Invoice.id == InvoicePartLink.invoice_id)
        .where(
            InvoicePartLink.plan_id == plan_id,
            InvoicePartLink.part_id.in_(part_ids),
        )
    )
    invoices_by_part: dict[int, list[dict]] = {p.part_id: [] for p in parts}
    for row in links_result.all():
        invoices_by_part.setdefault(row.part_id, []).append(
            {
                "link_id": row.link_id,
                "invoice_id": row.invoice_id,
                "invoice_no": row.invoice_no,
                "invoice_date": row.invoice_date.isoformat(),
                "supplier": row.supplier,
                "payment_date": row.payment_date.isoformat() if row.payment_date else None,
                "qty_covered": str(row.qty_covered) if row.qty_covered is not None else None,
                "is_carryover": bool(row.is_carryover),
            }
        )

    inventory_result = await session.execute(
        select(
            InventoryPlanAllocation.part_id,
            InventoryPlanAllocation.inventory_item_id,
            InventoryPlanAllocation.qty_covered,
            InventoryDocument.id.label("inventory_id"),
            InventoryDocument.month,
        )
        .join(InventoryItem, InventoryItem.id == InventoryPlanAllocation.inventory_item_id)
        .join(InventoryDocument, InventoryDocument.id == InventoryItem.inventory_id)
        .where(
            InventoryPlanAllocation.plan_id == plan_id,
            InventoryPlanAllocation.part_id.in_(part_ids),
        )
        .order_by(InventoryDocument.month, InventoryPlanAllocation.inventory_item_id)
    )
    inventory_by_part: dict[int, list[dict]] = {p.part_id: [] for p in parts}
    for row in inventory_result.all():
        inventory_by_part.setdefault(row.part_id, []).append(
            {
                "inventory_id": row.inventory_id,
                "inventory_item_id": row.inventory_item_id,
                "month": row.month.isoformat(),
                "qty_covered": str(row.qty_covered),
            }
        )

    # Load files for all plan parts in one query
    files_result = await session.execute(
        select(MonthlyPlanPartFile, FileModel)
        .join(FileModel, FileModel.id == MonthlyPlanPartFile.file_id)
        .where(MonthlyPlanPartFile.plan_part_id.in_([p.id for p in parts]))
        .order_by(MonthlyPlanPartFile.created_at)
    )
    files_by_plan_part: dict[int, list[dict]] = {p.id: [] for p in parts}
    for link, f in files_result.all():
        files_by_plan_part.setdefault(link.plan_part_id, []).append(
            {
                "id": f.id,
                "filename": f.filename,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
                "uploaded_at": f.uploaded_at.isoformat(),
            }
        )

    out = []
    for p in parts:
        qty_del = p.qty_delivered
        # Эффективная потребность — итоговая (qty_final), а не исходная расчётная (qty_required).
        req = p.qty_final
        invoices = invoices_by_part.get(p.part_id, [])
        inventory_allocations = inventory_by_part.get(p.part_id, [])
        qty_invoice_covered_total = sum(
            (Decimal(str(inv["qty_covered"])) for inv in invoices if inv["qty_covered"] is not None),
            Decimal("0"),
        )
        qty_inventory_covered_total = sum(
            (Decimal(item["qty_covered"]) for item in inventory_allocations),
            Decimal("0"),
        )
        qty_covered_total = qty_invoice_covered_total + qty_inventory_covered_total
        qty_available_total = min(req, qty_del + qty_inventory_covered_total)
        out.append(
            {
                "id": p.id,
                "plan_id": p.plan_id,
                "part_id": p.part_id,
                "qty_required": str(p.qty_required),
                "qty_final": str(p.qty_final),
                "qty_delivered": str(qty_del),
                "created_at": p.created_at.isoformat(),
                "has_invoice": len(invoices) > 0,
                "invoices": invoices,
                "has_inventory": len(inventory_allocations) > 0,
                "inventory_allocations": inventory_allocations,
                "qty_invoice_covered_total": str(qty_invoice_covered_total),
                "qty_inventory_covered_total": str(qty_inventory_covered_total),
                "qty_covered_total": str(qty_covered_total),
                "coverage_complete": bool(qty_covered_total >= req),
                "qty_available_total": str(qty_available_total),
                "delivery_complete": bool(qty_del + qty_inventory_covered_total >= req),
                "files": files_by_plan_part.get(p.id, []),
            }
        )
    return out


@router.get("/{plan_id}/parts-with-coverage")
async def list_plan_parts_with_coverage(
    plan_id: int,
    plan_part_ids: List[int] | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Returns all plan rows, or only requested rows, with coverage and files."""
    return await _plan_parts_with_coverage(
        plan_id,
        session,
        plan_part_ids=plan_part_ids,
    )


@router.get("/{plan_id}/parts/{plan_part_id}/with-coverage")
async def get_plan_part_with_coverage(
    plan_id: int,
    plan_part_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Returns one plan row so the UI can update it without rebuilding the page."""
    rows = await _plan_parts_with_coverage(
        plan_id,
        session,
        plan_part_id=plan_part_id,
    )
    return rows[0]
