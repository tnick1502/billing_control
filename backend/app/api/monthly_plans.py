from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart
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
        plan = await do_generate(session, data.month, data.order_status)
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
