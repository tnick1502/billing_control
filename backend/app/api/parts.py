from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Part
from app.models.bom import DeviceBomItem
from app.models.invoice import InvoicePartLink
from app.models.inventory import InventoryItem
from app.models.monthly_plan import MonthlyPlanPart
from app.models.order_part_item import OrderPartItem
from app.schemas.common import PartArchiveUpdate, PartCreate, PartRead, PartUpdate

router = APIRouter(prefix="/parts", tags=["parts"])


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _normalize_part_payload(data: dict) -> dict:
    for key in ("name", "cipher", "article", "part_type", "supplier", "description"):
        if key in data:
            data[key] = _clean_text(data[key])
    return data


async def _ensure_part_unique(
    session: AsyncSession,
    name: str,
    article: str | None,
    exclude_id: int | None = None,
) -> None:
    conditions = [
        func.lower(Part.name) == name.lower(),
        func.coalesce(func.lower(Part.article), "") == (article or "").lower(),
    ]
    if exclude_id is not None:
        conditions.append(Part.id != exclude_id)

    result = await session.execute(select(Part.id).where(*conditions).limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Деталь с таким наименованием и артикулом уже существует",
        )


async def _check_part_references(session: AsyncSession, part_id: int) -> list[str]:
    """Returns a list of human-readable descriptions of existing references."""
    refs: list[str] = []

    bom_count = await session.scalar(
        select(func.count()).where(DeviceBomItem.part_id == part_id)
    )
    if bom_count:
        refs.append(f"спецификации ({bom_count} шт.)")

    plan_count = await session.scalar(
        select(func.count()).where(MonthlyPlanPart.part_id == part_id)
    )
    if plan_count:
        refs.append(f"месячные планы ({plan_count} шт.)")

    invoice_count = await session.scalar(
        select(func.count()).where(InvoicePartLink.part_id == part_id)
    )
    if invoice_count:
        refs.append(f"счета ({invoice_count} шт.)")

    inventory_count = await session.scalar(
        select(func.count()).where(InventoryItem.part_id == part_id)
    )
    if inventory_count:
        refs.append(f"инвентаризации ({inventory_count} шт.)")

    order_count = await session.scalar(
        select(func.count()).where(OrderPartItem.part_id == part_id)
    )
    if order_count:
        refs.append(f"заказы ({order_count} шт.)")

    return refs


@router.get("", response_model=list[PartRead])
async def list_parts(
    include_archived: bool = Query(False, alias="include_archived"),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    q = select(Part).order_by(Part.id)
    if not include_archived:
        q = q.where(Part.is_archived == False)  # noqa: E712
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/types", response_model=list[str])
async def list_part_types(session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(
        select(Part.part_type)
        .where(Part.part_type.is_not(None), Part.is_archived == False)  # noqa: E712
        .distinct()
        .order_by(Part.part_type)
    )
    return [row for row in result.scalars().all() if row]


@router.get("/suppliers", response_model=list[str])
async def list_part_suppliers(session: AsyncSession = Depends(get_db, scope="function")):
    """Уникальные поставщики всех существующих деталей для подсказок в форме.

    Дедупликация выполняется без учёта регистра, чтобы старые варианты вроде
    ``ООО Ромашка`` и ``ооо ромашка`` не создавали две одинаковые подсказки.
    """
    result = await session.execute(
        select(Part.supplier)
        .where(Part.supplier.is_not(None))
        .order_by(func.lower(Part.supplier), Part.supplier)
    )
    suppliers: list[str] = []
    seen: set[str] = set()
    for raw in result.scalars().all():
        supplier = (raw or "").strip()
        key = supplier.casefold()
        if not supplier or key in seen:
            continue
        seen.add(key)
        suppliers.append(supplier)
    return suppliers


@router.post("", response_model=PartRead)
async def create_part(data: PartCreate, session: AsyncSession = Depends(get_db, scope="function")):
    dump = _normalize_part_payload(data.model_dump())
    if not dump.get("name"):
        raise HTTPException(status_code=400, detail="Наименование детали обязательно")
    await _ensure_part_unique(session, dump["name"], dump.get("article"))
    part = Part(**dump)
    session.add(part)
    await session.flush()
    await session.refresh(part)
    return part


@router.get("/{part_id}", response_model=PartRead)
async def get_part(part_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    return part


@router.patch("/{part_id}", response_model=PartRead)
async def update_part(part_id: int, data: PartUpdate, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    update_data = _normalize_part_payload(data.model_dump(exclude_unset=True))
    next_name = update_data.get("name", part.name)
    next_article = update_data.get("article", part.article)
    if not next_name:
        raise HTTPException(status_code=400, detail="Наименование детали обязательно")
    await _ensure_part_unique(session, next_name, next_article, exclude_id=part.id)
    for k, v in update_data.items():
        setattr(part, k, v)
    await session.flush()
    await session.refresh(part)
    return part


@router.patch("/{part_id}/archive", response_model=PartRead)
async def archive_part(part_id: int, data: PartArchiveUpdate, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    part.is_archived = data.is_archived
    await session.flush()
    await session.refresh(part)
    return part


@router.delete("/{part_id}", status_code=204)
async def delete_part(part_id: int, session: AsyncSession = Depends(get_db, scope="function")):
    result = await session.execute(select(Part).where(Part.id == part_id))
    part = result.scalar_one_or_none()
    if not part:
        raise HTTPException(404, "Part not found")
    refs = await _check_part_references(session, part_id)
    if refs:
        refs_str = ", ".join(refs)
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя удалить деталь: она используется в {refs_str}. Используйте архивирование.",
        )
    await session.delete(part)
    return None
