from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart, InvoicePartLink, Invoice
from app.schemas.common import (
    MonthlyPlanCreate,
    MonthlyPlanRead,
    MonthlyPlanUpdate,
    MonthlyPlanGenerate,
    MonthlyPlanDeviceRead,
    MonthlyPlanPartRead,
)
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
        plan = await do_generate(session, data.month, data.order_status, data.replace)
        await session.flush()
        await session.refresh(plan)
        return plan
    except ValueError as e:
        raise HTTPException(400, str(e))


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
    await session.delete(plan)
    return None


@router.get("/{plan_id}/devices", response_model=list[MonthlyPlanDeviceRead])
async def list_plan_devices(plan_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(MonthlyPlanDevice).where(MonthlyPlanDevice.plan_id == plan_id))
    return result.scalars().all()


@router.get("/{plan_id}/parts", response_model=list[MonthlyPlanPartRead])
async def list_plan_parts(plan_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id == plan_id))
    return result.scalars().all()


@router.get("/{plan_id}/parts-with-coverage")
async def list_plan_parts_with_coverage(plan_id: int, session: AsyncSession = Depends(get_db)):
    """Returns plan parts with invoice coverage (invoice_no for each part)."""
    parts_result = await session.execute(
        select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id == plan_id)
    )
    parts = list(parts_result.scalars().all())
    links_result = await session.execute(
        select(InvoicePartLink.part_id, InvoicePartLink.invoice_id, Invoice.invoice_no)
        .join(Invoice, Invoice.id == InvoicePartLink.invoice_id)
        .where(InvoicePartLink.plan_id == plan_id)
    )
    invoices_by_part: dict[int, list[dict]] = {p.part_id: [] for p in parts}
    for row in links_result.all():
        invoices_by_part.setdefault(row.part_id, []).append(
            {"invoice_id": row.invoice_id, "invoice_no": row.invoice_no}
        )
    return [
        {
            "id": p.id,
            "plan_id": p.plan_id,
            "part_id": p.part_id,
            "qty_required": str(p.qty_required),
            "qty_final": str(p.qty_final),
            "created_at": p.created_at.isoformat(),
            "has_invoice": len(invoices_by_part.get(p.part_id, [])) > 0,
            "invoices": invoices_by_part.get(p.part_id, []),
        }
        for p in parts
    ]
