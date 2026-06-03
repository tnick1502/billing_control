"""Сквозной перенос остатков деталей между месячными планами («дельта»).

Идея: если по детали в каком-то месяце заказали счетами больше, чем требовалось,
излишек переносится в следующие месяцы (FIFO по дате счёта) и автоматически
закрывает их потребность, создавая привязку счёта-источника к детали в новом плане.

Перенос считается сквозным по всем месяцам, поэтому пересобирается целиком при любом
изменении планов или ручных привязок счетов (см. recompute_carryover_links).
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Invoice,
    InvoicePartLink,
    MonthlyPlan,
    MonthlyPlanPart,
    Part,
)

log = logging.getLogger(__name__)

ZERO = Decimal("0")


@dataclass
class CarryoverResult:
    # Месяцы (первый день месяца) по возрастанию
    months: list[date]
    # part_id -> метаданные детали
    parts: dict[int, dict]
    # part_id -> { month -> остаток на конец месяца }
    balances: dict[int, dict[date, Decimal]]
    # part_id -> { month -> недозаказ за месяц (без учёта переносов) }
    undersupply: dict[int, dict[date, Decimal]]
    # part_id -> { month -> перезаказ за месяц (излишек, ставший остатком) }
    overorders: dict[int, dict[date, Decimal]]
    # Привязки, которые надо создать как авто-перенос: (invoice_id, plan_id, part_id, qty)
    links_to_create: list[tuple[int, int, int, Decimal]] = field(default_factory=list)


async def compute_carryover(session: AsyncSession) -> CarryoverResult:
    """Посчитать перенос остатков по всем планам. Только чтение, без записи в БД."""
    # Один план на месяц — берём максимальную ревизию
    plans_res = await session.execute(
        select(MonthlyPlan.id, MonthlyPlan.month, MonthlyPlan.revision).order_by(
            MonthlyPlan.month, MonthlyPlan.revision
        )
    )
    plan_by_month: dict[date, int] = {}
    for plan_id, month, _revision in plans_res.all():
        plan_by_month[month] = plan_id  # последний (max revision) перезапишет предыдущие
    months = sorted(plan_by_month.keys())
    plan_ids = [plan_by_month[m] for m in months]
    # plan_id -> month, для обратного сопоставления привязок
    month_by_plan = {pid: m for m, pid in plan_by_month.items()}

    result = CarryoverResult(
        months=months, parts={}, balances={}, undersupply={}, overorders={}, links_to_create=[]
    )
    if not plan_ids:
        return result

    # Потребность: part_id -> { month -> qty_required }
    required: dict[int, dict[date, Decimal]] = {}
    parts_res = await session.execute(
        select(MonthlyPlanPart.plan_id, MonthlyPlanPart.part_id, MonthlyPlanPart.qty_required).where(
            MonthlyPlanPart.plan_id.in_(plan_ids)
        )
    )
    for plan_id, part_id, qty_required in parts_res.all():
        month = month_by_plan.get(plan_id)
        if month is None:
            continue
        required.setdefault(part_id, {})[month] = Decimal(qty_required)

    # Ручные привязки счетов: part_id -> { month -> [(invoice_date, invoice_id, qty_covered)] }
    manual: dict[int, dict[date, list[tuple[date, int, Decimal]]]] = {}
    links_res = await session.execute(
        select(
            InvoicePartLink.plan_id,
            InvoicePartLink.part_id,
            InvoicePartLink.invoice_id,
            InvoicePartLink.qty_covered,
            Invoice.invoice_date,
        )
        .join(Invoice, Invoice.id == InvoicePartLink.invoice_id)
        .where(
            InvoicePartLink.plan_id.in_(plan_ids),
            InvoicePartLink.is_carryover.is_(False),
        )
    )
    for plan_id, part_id, invoice_id, qty_covered, invoice_date in links_res.all():
        month = month_by_plan.get(plan_id)
        if month is None:
            continue
        qty = Decimal(qty_covered) if qty_covered is not None else ZERO
        manual.setdefault(part_id, {}).setdefault(month, []).append((invoice_date, invoice_id, qty))

    # Метаданные деталей
    part_ids = set(required.keys()) | set(manual.keys())
    if part_ids:
        meta_res = await session.execute(
            select(Part.id, Part.name, Part.part_type).where(Part.id.in_(part_ids))
        )
        for pid, name, part_type in meta_res.all():
            result.parts[pid] = {"part_id": pid, "name": name, "part_type": part_type}

    # Прогон по месяцам для каждой детали
    for part_id in part_ids:
        result.balances[part_id] = {}
        result.undersupply[part_id] = {}
        result.overorders[part_id] = {}
        req_by_month = required.get(part_id, {})
        manual_by_month = manual.get(part_id, {})
        # FIFO-лоты остатка: [[invoice_id, remaining]]
        lots: list[list] = []

        for month in months:
            plan_id = plan_by_month[month]
            need = req_by_month.get(month, ZERO)
            month_manual = sorted(manual_by_month.get(month, []), key=lambda t: (t[0], t[1]))
            manual_total = sum((q for _, _, q in month_manual), ZERO)

            # Шаг A: перенос покрывает потребность первым (старые счета первыми)
            remaining_need = need
            for lot in lots:
                if remaining_need <= ZERO:
                    break
                take = min(lot[1], remaining_need)
                if take > ZERO:
                    lot[1] -= take
                    remaining_need -= take
                    result.links_to_create.append((lot[0], plan_id, part_id, take))
            lots = [lot for lot in lots if lot[1] > ZERO]

            # Шаг B: свои счета месяца добивают остаток потребности, излишек → новые лоты
            overorder = ZERO
            for _inv_date, invoice_id, qty in month_manual:
                avail = qty
                if remaining_need > ZERO:
                    used = min(avail, remaining_need)
                    remaining_need -= used
                    avail -= used
                if avail > ZERO:
                    lots.append([invoice_id, avail])
                    overorder += avail

            result.overorders[part_id][month] = overorder
            result.balances[part_id][month] = sum((lot[1] for lot in lots), ZERO)
            # Недозаказ — без учёта переносов: потребность минус ручной заказ месяца
            shortfall = need - manual_total
            result.undersupply[part_id][month] = shortfall if shortfall > ZERO else ZERO

    return result


async def recompute_carryover_links(session: AsyncSession) -> None:
    """Пересобрать авто-привязки переноса остатков по всем планам."""
    await session.execute(delete(InvoicePartLink).where(InvoicePartLink.is_carryover.is_(True)))
    await session.flush()

    result = await compute_carryover(session)
    if not result.links_to_create:
        return

    # Свернуть по (invoice, plan, part): один счёт может закрыть деталь несколькими лотами
    aggregated: dict[tuple[int, int, int], Decimal] = {}
    for invoice_id, plan_id, part_id, qty in result.links_to_create:
        key = (invoice_id, plan_id, part_id)
        aggregated[key] = aggregated.get(key, ZERO) + qty

    # Существующие ручные привязки (invoice, plan, part) — не конфликтуем с уникальным ограничением
    existing_res = await session.execute(
        select(InvoicePartLink.invoice_id, InvoicePartLink.plan_id, InvoicePartLink.part_id)
    )
    existing = {(i, p, pa) for i, p, pa in existing_res.all()}

    for (invoice_id, plan_id, part_id), qty in aggregated.items():
        key = (invoice_id, plan_id, part_id)
        if key in existing:
            log.warning(
                "carryover: пропуск авто-привязки (invoice=%s, plan=%s, part=%s) — уже есть привязка",
                invoice_id, plan_id, part_id,
            )
            continue
        session.add(
            InvoicePartLink(
                invoice_id=invoice_id,
                plan_id=plan_id,
                part_id=part_id,
                qty_covered=qty,
                note="Перенос остатка",
                is_carryover=True,
            )
        )
    await session.flush()
