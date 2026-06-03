from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart, InvoicePartLink, Invoice
from app.models.monthly_plan import MonthlyPlanPartFile
from app.models.invoice import File as FileModel
from app.schemas.common import (
    FileRead,
    MonthlyPlanCreate,
    MonthlyPlanRead,
    MonthlyPlanUpdate,
    MonthlyPlanGenerate,
    MonthlyPlanDeviceRead,
    MonthlyPlanPartRead,
    MonthlyPlanPartQtyDeliveredUpdate,
)
from app.services.carryover import compute_carryover, recompute_carryover_links
from app.services.file_storage import delete_orphaned_files, save_upload_as_file
from app.services.monthly_plan import generate_monthly_plan as do_generate

router = APIRouter(prefix="/monthly-plans", tags=["monthly-plans"])


@router.get("", response_model=list[MonthlyPlanRead])
async def list_monthly_plans(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(MonthlyPlan).order_by(MonthlyPlan.month.desc()))
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

    - remainders: детали с остатком > 0 на конец последнего месяца; по каждой — разбивка
      перезаказа по месяцам (в каком месяце сколько было заказано сверх потребности).
    - undersupply: детали с недозаказом за текущий (последний) месяц, без учёта переносов.

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
        under = result.undersupply.get(part_id, {})

        remainder = balances.get(current, Decimal("0"))
        if remainder > 0:
            remainders.append(
                {
                    "part_id": part_id,
                    "name": meta["name"],
                    "part_type": meta["part_type"],
                    "remainder": str(remainder),
                    "overorders": {
                        m.isoformat(): str(v) for m, v in sorted(overorders.items()) if v > 0
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


@router.get("/{plan_id}", response_model=MonthlyPlanRead)
async def get_monthly_plan(plan_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(MonthlyPlan).where(MonthlyPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Monthly plan not found")
    return plan


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
    result = await session.execute(select(MonthlyPlan).where(MonthlyPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Monthly plan not found")
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


@router.patch("/{plan_id}/parts/{plan_part_id}", response_model=MonthlyPlanPartRead)
async def update_plan_part_qty_delivered(
    plan_id: int,
    plan_part_id: int,
    data: MonthlyPlanPartQtyDeliveredUpdate,
    session: AsyncSession = Depends(get_db),
):
    """Фактически поставленное количество по строке плана (0 … требуется)."""
    result = await session.execute(
        select(MonthlyPlanPart).where(
            MonthlyPlanPart.id == plan_part_id,
            MonthlyPlanPart.plan_id == plan_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Строка плана не найдена")
    q = data.qty_delivered
    if q < 0 or q > row.qty_required:
        raise HTTPException(400, "Поставлено должно быть от 0 до «Требуется»")
    row.qty_delivered = q
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


@router.get("/{plan_id}/parts-with-coverage")
async def list_plan_parts_with_coverage(plan_id: int, session: AsyncSession = Depends(get_db)):
    """Returns plan parts with invoice coverage and attached delivery files."""
    if not await session.get(MonthlyPlan, plan_id):
        raise HTTPException(404, "Monthly plan not found")
    parts_result = await session.execute(
        select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id == plan_id)
    )
    parts = list(parts_result.scalars().all())
    links_result = await session.execute(
        select(
            InvoicePartLink.id.label("link_id"),
            InvoicePartLink.part_id,
            InvoicePartLink.invoice_id,
            Invoice.invoice_no,
            Invoice.supplier,
            Invoice.payment_date,
            InvoicePartLink.qty_covered,
            InvoicePartLink.is_carryover,
        )
        .join(Invoice, Invoice.id == InvoicePartLink.invoice_id)
        .where(InvoicePartLink.plan_id == plan_id)
    )
    invoices_by_part: dict[int, list[dict]] = {p.part_id: [] for p in parts}
    for row in links_result.all():
        invoices_by_part.setdefault(row.part_id, []).append(
            {
                "link_id": row.link_id,
                "invoice_id": row.invoice_id,
                "invoice_no": row.invoice_no,
                "supplier": row.supplier,
                "payment_date": row.payment_date.isoformat() if row.payment_date else None,
                "qty_covered": str(row.qty_covered) if row.qty_covered is not None else None,
                "is_carryover": bool(row.is_carryover),
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
        req = p.qty_required
        invoices = invoices_by_part.get(p.part_id, [])
        qty_covered_total = sum(
            (Decimal(str(inv["qty_covered"])) for inv in invoices if inv["qty_covered"] is not None),
            Decimal("0"),
        )
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
                "qty_covered_total": str(qty_covered_total),
                "coverage_complete": bool(qty_covered_total >= req),
                "delivery_complete": bool(qty_del >= req),
                "files": files_by_plan_part.get(p.id, []),
            }
        )
    return out
