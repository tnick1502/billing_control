"""Сквозной учёт остатков деталей между месячными планами.

Источники остатка: излишки ручных привязок счетов и положительные результаты
проведённой инвентаризации. Они хранятся раздельными FIFO-лотами и автоматически
закрывают потребность следующих месяцев, сохраняя происхождение количества.

Перенос считается сквозным по всем месяцам, поэтому пересобирается целиком при любом
изменении планов или ручных привязок счетов (см. recompute_carryover_links).
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Invoice,
    InvoicePartLink,
    InventoryDocument,
    InventoryItem,
    InventoryPlanAllocation,
    MonthlyPlan,
    MonthlyPlanPart,
    Part,
)

log = logging.getLogger(__name__)

ZERO = Decimal("0")

# Произвольный фиксированный ключ для pg_advisory_xact_lock: сериализует генерацию планов
# и пересчёт переносов между собой, чтобы конкурентные запросы не ломали уникальные ограничения.
CARRYOVER_LOCK_KEY = 478223901


async def acquire_carryover_lock(session: AsyncSession) -> None:
    """Взять транзакционную advisory-блокировку (PostgreSQL). На sqlite — no-op.

    Блокировка держится до конца транзакции (commit/rollback), повторный вызов в той же
    транзакции безопасен. Любой конкурентный писатель ждёт здесь, а не падает на дубле.
    """
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=CARRYOVER_LOCK_KEY))


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
    # part_id -> { month -> найдено дополнительно при проведённой инвентаризации }
    inventory_additions: dict[int, dict[date, Decimal]]
    # part_id -> { month -> сколько инвентаризационного остатка закрыло потребность }
    inventory_consumed: dict[int, dict[date, Decimal]]
    # part_id -> { month -> остаток на конец месяца отдельно по источникам }
    invoice_balances: dict[int, dict[date, Decimal]]
    inventory_balances: dict[int, dict[date, Decimal]]
    # Привязки, которые надо создать как авто-перенос: (invoice_id, plan_id, part_id, qty)
    links_to_create: list[tuple[int, int, int, Decimal]] = field(default_factory=list)
    # Автораспределения инвентаризации: (inventory_item_id, plan_id, part_id, qty)
    inventory_allocations_to_create: list[tuple[int, int, int, Decimal]] = field(default_factory=list)


@dataclass
class StockLot:
    source_kind: str  # invoice | inventory
    source_id: int
    remaining: Decimal


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
        months=months,
        parts={},
        balances={},
        undersupply={},
        overorders={},
        inventory_additions={},
        inventory_consumed={},
        invoice_balances={},
        inventory_balances={},
        links_to_create=[],
        inventory_allocations_to_create=[],
    )
    if not plan_ids:
        return result

    # Потребность берём из qty_final — это итоговая потребность к закупке (с учётом ручной
    # корректировки плановиком); по умолчанию qty_final == qty_required.
    required: dict[int, dict[date, Decimal]] = {}
    parts_res = await session.execute(
        select(MonthlyPlanPart.plan_id, MonthlyPlanPart.part_id, MonthlyPlanPart.qty_final).where(
            MonthlyPlanPart.plan_id.in_(plan_ids)
        )
    )
    for plan_id, part_id, qty_final in parts_res.all():
        month = month_by_plan.get(plan_id)
        if month is None:
            continue
        required.setdefault(part_id, {})[month] = Decimal(qty_final)

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

    # Проведённые инвентаризации — самостоятельные физические FIFO-лоты. Документ
    # относится к календарному месяцу и не зависит от ревизии плана.
    inventory: dict[int, dict[date, list[tuple[int, Decimal]]]] = {}
    inventory_res = await session.execute(
        select(
            InventoryDocument.month,
            InventoryItem.id,
            InventoryItem.part_id,
            InventoryItem.qty_found,
        )
        .join(InventoryItem, InventoryItem.inventory_id == InventoryDocument.id)
        .where(
            InventoryDocument.status == "posted",
            InventoryDocument.month.in_(months),
        )
        .order_by(InventoryDocument.month, InventoryItem.id)
    )
    for month, item_id, part_id, qty_found in inventory_res.all():
        inventory.setdefault(part_id, {}).setdefault(month, []).append(
            (item_id, Decimal(qty_found))
        )

    # Метаданные деталей
    part_ids = set(required.keys()) | set(manual.keys()) | set(inventory.keys())
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
        result.inventory_additions[part_id] = {}
        result.inventory_consumed[part_id] = {}
        result.invoice_balances[part_id] = {}
        result.inventory_balances[part_id] = {}
        req_by_month = required.get(part_id, {})
        manual_by_month = manual.get(part_id, {})
        inventory_by_month = inventory.get(part_id, {})
        lots: list[StockLot] = []

        for month in months:
            plan_id = plan_by_month[month]
            need = req_by_month.get(month, ZERO)
            month_manual = sorted(manual_by_month.get(month, []), key=lambda t: (t[0], t[1]))
            month_inventory = inventory_by_month.get(month, [])
            inventory_added = sum((qty for _, qty in month_inventory), ZERO)
            inventory_used = ZERO

            # Шаг A: старые физические/счётные остатки закрывают потребность первыми.
            remaining_need = need
            for lot in lots:
                if remaining_need <= ZERO:
                    break
                take = min(lot.remaining, remaining_need)
                if take > ZERO:
                    lot.remaining -= take
                    remaining_need -= take
                    if lot.source_kind == "invoice":
                        result.links_to_create.append((lot.source_id, plan_id, part_id, take))
                    else:
                        inventory_used += take
                        result.inventory_allocations_to_create.append(
                            (lot.source_id, plan_id, part_id, take)
                        )
            lots = [lot for lot in lots if lot.remaining > ZERO]

            # Шаг B: уже привязанные к месяцу счета закрывают потребность. Инвентаризация
            # не должна задним числом вытеснять такой счёт из плана и превращать его в
            # ложный перезаказ — особенно если поставка по нему уже отмечена.
            overorder = ZERO
            for _inv_date, invoice_id, qty in month_manual:
                avail = qty
                if remaining_need > ZERO:
                    used = min(avail, remaining_need)
                    remaining_need -= used
                    avail -= used
                if avail > ZERO:
                    lots.append(StockLot("invoice", invoice_id, avail))
                    overorder += avail

            # Шаг C: найденное в этом месяце закрывает только оставшуюся после счетов
            # потребность. Неиспользованное количество становится физическим остатком.
            for inventory_item_id, qty in month_inventory:
                avail = qty
                if remaining_need > ZERO:
                    used = min(avail, remaining_need)
                    if used > ZERO:
                        remaining_need -= used
                        avail -= used
                        inventory_used += used
                        result.inventory_allocations_to_create.append(
                            (inventory_item_id, plan_id, part_id, used)
                        )
                if avail > ZERO:
                    lots.append(StockLot("inventory", inventory_item_id, avail))

            result.overorders[part_id][month] = overorder
            result.inventory_additions[part_id][month] = inventory_added
            result.inventory_consumed[part_id][month] = inventory_used
            invoice_balance = sum(
                (lot.remaining for lot in lots if lot.source_kind == "invoice"), ZERO
            )
            inventory_balance = sum(
                (lot.remaining for lot in lots if lot.source_kind == "inventory"), ZERO
            )
            result.invoice_balances[part_id][month] = invoice_balance
            result.inventory_balances[part_id][month] = inventory_balance
            result.balances[part_id][month] = invoice_balance + inventory_balance
            # Фактический недозаказ: после учёта старых остатков, найденного на
            # инвентаризации и ручных счетов текущего месяца.
            result.undersupply[part_id][month] = remaining_need

    return result


async def recompute_carryover_links(session: AsyncSession) -> None:
    """Пересобрать авто-привязки переноса остатков по всем планам.

    Полностью сериализовано advisory-блокировкой: конкурентные изменения счетов/планов
    выстраиваются в очередь, а не наступают друг на друга (иначе — гонки и нарушение
    уникального ограничения invoice_part_links).
    """
    await acquire_carryover_lock(session)
    await session.execute(delete(InvoicePartLink).where(InvoicePartLink.is_carryover.is_(True)))
    await session.execute(delete(InventoryPlanAllocation))
    await session.flush()

    result = await compute_carryover(session)

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

    inventory_aggregated: dict[tuple[int, int, int], Decimal] = {}
    for inventory_item_id, plan_id, part_id, qty in result.inventory_allocations_to_create:
        key = (inventory_item_id, plan_id, part_id)
        inventory_aggregated[key] = inventory_aggregated.get(key, ZERO) + qty

    for (inventory_item_id, plan_id, part_id), qty in inventory_aggregated.items():
        session.add(
            InventoryPlanAllocation(
                inventory_item_id=inventory_item_id,
                plan_id=plan_id,
                part_id=part_id,
                qty_covered=qty,
            )
        )
    await session.flush()

    # qty_delivered хранит только поставку по счетам. Если новый пересчёт отдал часть
    # потребности физическому остатку из инвентаризации, старое ручное значение могло
    # оказаться выше оставшейся потребности и дать двойной физический учёт. Подрезаем
    # только превышение; при отмене инвентаризации значение автоматически не растёт.
    if inventory_aggregated:
        allocation_res = await session.execute(
            select(
                InventoryPlanAllocation.plan_id,
                InventoryPlanAllocation.part_id,
                func.sum(InventoryPlanAllocation.qty_covered),
            ).group_by(
                InventoryPlanAllocation.plan_id,
                InventoryPlanAllocation.part_id,
            )
        )
        inventory_by_plan_part = {
            (plan_id, part_id): Decimal(qty)
            for plan_id, part_id, qty in allocation_res.all()
        }
        affected_plan_ids = {plan_id for plan_id, _part_id in inventory_by_plan_part}
        plan_parts_res = await session.execute(
            select(MonthlyPlanPart).where(MonthlyPlanPart.plan_id.in_(affected_plan_ids))
        )
        for plan_part in plan_parts_res.scalars().all():
            inventory_qty = inventory_by_plan_part.get(
                (plan_part.plan_id, plan_part.part_id), ZERO
            )
            max_invoice_delivery = max(plan_part.qty_final - inventory_qty, ZERO)
            if plan_part.qty_delivered > max_invoice_delivery:
                plan_part.qty_delivered = max_invoice_delivery
        await session.flush()
