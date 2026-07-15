from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import xlsxwriter


NO_GROUP_LABEL = "Без типа"


@dataclass(frozen=True)
class PlanExportMeta:
    id: int
    month: date
    revision: int
    status: str
    generated_at: datetime
    generated_by: str | None
    note: str | None


@dataclass(frozen=True)
class PlanDeviceExportRow:
    device_id: int
    name: str
    model: str | None
    qty_total: Decimal
    bom_version: int
    bom_name: str | None
    bom_status: str


@dataclass(frozen=True)
class PlanPartExportRow:
    part_id: int
    name: str
    cipher: str | None
    article: str | None
    part_type: str | None
    qty_required: Decimal
    qty_final: Decimal
    qty_covered: Decimal
    qty_delivered: Decimal


@dataclass(frozen=True)
class PlanInvoiceExportRow:
    part_id: int
    part_name: str
    cipher: str | None
    part_type: str | None
    invoice_no: str
    invoice_date: date
    supplier: str | None
    qty_covered: Decimal
    payment_date: date | None
    is_carryover: bool


def _decimal_number(value: Decimal) -> float:
    return float(value)


def _is_integral(value: Decimal) -> bool:
    """Целое ли количество — от этого зависит числовой формат ячейки (как formatQty в UI)."""
    try:
        return Decimal(value) == Decimal(value).to_integral_value()
    except Exception:
        return True


def _group_name(value: str | None) -> str:
    cleaned = (value or "").strip()
    return cleaned or NO_GROUP_LABEL


def _group_sort_key(value: str) -> tuple[int, str]:
    return (1 if value == NO_GROUP_LABEL else 0, value.casefold())


def _ru_month(value: date) -> str:
    names = (
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    )
    return f"{names[value.month - 1]} {value.year}"


def _date_text(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def _status_label(value: str) -> str:
    labels = {
        "draft": "Черновик",
        "current": "Текущая",
        "active": "Активна",
        "archived": "Архив",
    }
    return labels.get(value.strip().lower(), value)


def build_monthly_plan_xlsx(
    plan: PlanExportMeta,
    devices: list[PlanDeviceExportRow],
    parts: list[PlanPartExportRow],
    invoices: list[PlanInvoiceExportRow],
) -> bytes:
    """Build a self-contained, auditable Excel workbook for one monthly plan."""
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    workbook.set_properties(
        {
            "title": f"Месячный план — {_ru_month(plan.month)}",
            "subject": "План закупки деталей по производственным заказам",
            "author": "Billing Control",
            "company": "Billing Control",
            "comments": "Сформировано автоматически из месячного плана Billing Control",
        }
    )

    colors = {
        "navy": "#17324D",
        "blue": "#245B78",
        "teal": "#0F766E",
        "light_blue": "#DCEAF3",
        "light_teal": "#DDF2EE",
        "light_gray": "#EEF2F5",
        "mid_gray": "#D1D9E0",
        "text": "#17212B",
        "muted": "#5B6873",
        "white": "#FFFFFF",
        "green": "#E3F3E8",
        "green_text": "#237A3B",
        "red": "#FBE6E8",
        "red_text": "#A6323E",
        "amber": "#FFF1CC",
        "amber_text": "#8A5A00",
    }

    title_fmt = workbook.add_format(
        {
            "font_name": "Aptos Display",
            "font_size": 20,
            "bold": True,
            "font_color": colors["white"],
            "bg_color": colors["navy"],
            "align": "left",
            "valign": "vcenter",
        }
    )
    subtitle_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "font_color": colors["light_blue"],
            "bg_color": colors["navy"],
            "align": "left",
            "valign": "vcenter",
        }
    )
    header_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "bold": True,
            "font_color": colors["white"],
            "bg_color": colors["blue"],
            "border": 1,
            "border_color": colors["blue"],
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        }
    )
    label_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "bold": True,
            "font_color": colors["muted"],
            "bg_color": colors["light_gray"],
            "align": "left",
            "valign": "vcenter",
        }
    )
    value_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "font_color": colors["text"],
            "bg_color": colors["white"],
            "align": "left",
            "valign": "vcenter",
        }
    )
    body_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "font_color": colors["text"],
            "bottom": 1,
            "bottom_color": colors["mid_gray"],
            "valign": "vcenter",
        }
    )
    body_center_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "font_color": colors["text"],
            "bottom": 1,
            "bottom_color": colors["mid_gray"],
            "align": "center",
            "valign": "vcenter",
        }
    )
    id_fmt = workbook.add_format(
        {
            "font_name": "Aptos Mono",
            "font_size": 9,
            "font_color": colors["muted"],
            "bottom": 1,
            "bottom_color": colors["mid_gray"],
            "align": "center",
        }
    )
    _qty_base = {
        "font_name": "Aptos Mono",
        "font_size": 10,
        "font_color": colors["text"],
        "bottom": 1,
        "bottom_color": colors["mid_gray"],
        "align": "right",
    }
    qty_fmt = workbook.add_format({**_qty_base, "num_format": "#,##0"})
    qty_frac_fmt = workbook.add_format({**_qty_base, "num_format": "#,##0.00"})

    def _qty_format(value: Decimal):
        """Целые количества — без дробной части, дробные — с двумя знаками (как в UI)."""
        return qty_fmt if _is_integral(value) else qty_frac_fmt
    group_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 11,
            "bold": True,
            "font_color": colors["navy"],
            "bg_color": colors["light_blue"],
            "top": 1,
            "bottom": 1,
            "border_color": colors["blue"],
            "valign": "vcenter",
        }
    )
    subtotal_label_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "bold": True,
            "font_color": colors["text"],
            "bg_color": colors["light_gray"],
            "top": 1,
            "top_color": colors["mid_gray"],
            "align": "right",
        }
    )
    _subtotal_base = {
        "font_name": "Aptos Mono",
        "font_size": 10,
        "bold": True,
        "font_color": colors["text"],
        "bg_color": colors["light_gray"],
        "top": 1,
        "top_color": colors["mid_gray"],
        "align": "right",
    }
    subtotal_qty_fmt = workbook.add_format({**_subtotal_base, "num_format": "#,##0"})
    subtotal_qty_frac_fmt = workbook.add_format({**_subtotal_base, "num_format": "#,##0.00"})

    def _subtotal_format(value: Decimal):
        return subtotal_qty_fmt if _is_integral(value) else subtotal_qty_frac_fmt
    kpi_label_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 10,
            "bold": True,
            "font_color": colors["muted"],
            "bg_color": colors["light_teal"],
            "align": "center",
            "valign": "vcenter",
            "top": 1,
            "left": 1,
            "right": 1,
            "border_color": colors["teal"],
        }
    )
    _kpi_value_base = {
        "font_name": "Aptos Display",
        "font_size": 18,
        "bold": True,
        "font_color": colors["teal"],
        "bg_color": colors["light_teal"],
        "align": "center",
        "valign": "vcenter",
        "bottom": 1,
        "left": 1,
        "right": 1,
        "border_color": colors["teal"],
    }
    kpi_value_fmt = workbook.add_format({**_kpi_value_base, "num_format": "#,##0"})
    kpi_value_frac_fmt = workbook.add_format({**_kpi_value_base, "num_format": "#,##0.00"})

    def _kpi_format(value: Decimal):
        return kpi_value_fmt if _is_integral(value) else kpi_value_frac_fmt
    note_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 9,
            "font_color": colors["muted"],
            "bg_color": colors["light_gray"],
            "text_wrap": True,
            "valign": "top",
        }
    )
    status_ok_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 9,
            "bold": True,
            "font_color": colors["green_text"],
            "bg_color": colors["green"],
            "bottom": 1,
            "bottom_color": colors["mid_gray"],
            "align": "center",
        }
    )
    status_bad_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 9,
            "bold": True,
            "font_color": colors["red_text"],
            "bg_color": colors["red"],
            "bottom": 1,
            "bottom_color": colors["mid_gray"],
            "align": "center",
        }
    )
    status_pending_fmt = workbook.add_format(
        {
            "font_name": "Aptos",
            "font_size": 9,
            "bold": True,
            "font_color": colors["amber_text"],
            "bg_color": colors["amber"],
            "bottom": 1,
            "bottom_color": colors["mid_gray"],
            "align": "center",
        }
    )

    grouped_parts: dict[str, list[PlanPartExportRow]] = defaultdict(list)
    for part in parts:
        grouped_parts[_group_name(part.part_type)].append(part)
    group_names = sorted(grouped_parts, key=_group_sort_key)
    for rows in grouped_parts.values():
        rows.sort(key=lambda item: (item.name.casefold(), (item.cipher or "").casefold(), item.part_id))

    # Created first so the summary is the left-most sheet in Excel.
    summary = workbook.add_worksheet("Сводка")

    # Sheet: parts. Built first so summary formulas can reference exact populated ranges.
    details = workbook.add_worksheet("Детали")
    details.hide_gridlines(2)
    details.set_tab_color(colors["teal"])
    details.set_landscape()
    details.fit_to_pages(1, 0)
    details.set_margins(0.25, 0.25, 0.4, 0.4)
    details.repeat_rows(0, 4)
    details.merge_range("A1:M1", f"Месячный план деталей — {_ru_month(plan.month)}", title_fmt)
    details.merge_range("A2:M2", f"План №{plan.id} · ревизия {plan.revision} · статус: {_status_label(plan.status)}", subtitle_fmt)
    details.set_row(0, 32)
    details.set_row(1, 22)
    details.merge_range("A4:M4", "Группы расположены по алфавиту; строки каждой группы можно свернуть средствами структуры Excel.", note_fmt)
    detail_headers = [
        "№",
        "ID",
        "Деталь",
        "Шифр",
        "Артикул",
        "Расчётная потребность",
        "Итого к закупке",
        "Покрыто счетами",
        "Осталось покрыть",
        "Поставлено",
        "Осталось поставить",
        "Статус счетов",
        "Статус поставки",
    ]
    details.write_row(4, 0, detail_headers, header_fmt)
    details.set_row(4, 42)
    details.set_column("A:A", 5)
    details.set_column("B:B", 8)
    details.set_column("C:C", 34)
    details.set_column("D:E", 22)
    details.set_column("F:K", 15)
    details.set_column("L:M", 15)
    details.freeze_panes(5, 2)

    row = 5
    detail_number = 1
    for group_name in group_names:
        group_rows = grouped_parts[group_name]
        details.merge_range(row, 0, row, 12, f"{group_name}  ·  {len(group_rows)} поз.", group_fmt)
        details.set_row(row, 24)
        row += 1
        group_start_row = row
        for part in group_rows:
            excel_row = row + 1
            details.write_number(row, 0, detail_number, body_center_fmt)
            details.write_number(row, 1, part.part_id, id_fmt)
            details.write(row, 2, part.name, body_fmt)
            details.write(row, 3, part.cipher or "—", body_fmt)
            details.write(row, 4, part.article or "—", body_fmt)
            details.write_number(row, 5, _decimal_number(part.qty_required), _qty_format(part.qty_required))
            details.write_number(row, 6, _decimal_number(part.qty_final), _qty_format(part.qty_final))
            details.write_number(row, 7, _decimal_number(part.qty_covered), _qty_format(part.qty_covered))
            remaining_coverage = max(part.qty_final - part.qty_covered, Decimal("0"))
            details.write_formula(row, 8, f"=MAX(G{excel_row}-H{excel_row},0)", _qty_format(remaining_coverage), _decimal_number(remaining_coverage))
            details.write_number(row, 9, _decimal_number(part.qty_delivered), _qty_format(part.qty_delivered))
            remaining_delivery = max(part.qty_final - part.qty_delivered, Decimal("0"))
            details.write_formula(row, 10, f"=MAX(G{excel_row}-J{excel_row},0)", _qty_format(remaining_delivery), _decimal_number(remaining_delivery))
            coverage_ok = part.qty_covered >= part.qty_final
            delivery_ok = part.qty_delivered >= part.qty_final
            details.write_formula(
                row,
                11,
                f'=IF(H{excel_row}>=G{excel_row},"Покрыто","Не покрыто")',
                status_ok_fmt if coverage_ok else status_bad_fmt,
                "Покрыто" if coverage_ok else "Не покрыто",
            )
            details.write_formula(
                row,
                12,
                f'=IF(J{excel_row}>=G{excel_row},"Поставлено","Не поставлено")',
                status_ok_fmt if delivery_ok else status_bad_fmt,
                "Поставлено" if delivery_ok else "Не поставлено",
            )
            details.set_row(row, 21, None, {"level": 1})
            detail_number += 1
            row += 1

        group_end_row = row
        first_excel = group_start_row + 1
        last_excel = group_end_row
        details.merge_range(row, 0, row, 4, f"Итого по группе «{group_name}»", subtotal_label_fmt)
        zero = Decimal("0")
        group_totals: dict[int, Decimal] = {
            5: sum((p.qty_required for p in group_rows), zero),
            6: sum((p.qty_final for p in group_rows), zero),
            7: sum((p.qty_covered for p in group_rows), zero),
            8: sum((max(p.qty_final - p.qty_covered, zero) for p in group_rows), zero),
            9: sum((p.qty_delivered for p in group_rows), zero),
            10: sum((max(p.qty_final - p.qty_delivered, zero) for p in group_rows), zero),
        }
        for col, total in group_totals.items():
            col_letter = xlsxwriter.utility.xl_col_to_name(col)
            details.write_formula(
                row,
                col,
                f"=SUM({col_letter}{first_excel}:{col_letter}{last_excel})",
                _subtotal_format(total),
                _decimal_number(total),
            )
        details.write_blank(row, 11, None, subtotal_label_fmt)
        details.write_blank(row, 12, None, subtotal_label_fmt)
        details.set_row(row, 22)
        row += 1

    if not parts:
        details.merge_range(row, 0, row + 1, 12, "В плане нет деталей", note_fmt)
        row += 2
    details.autofilter(4, 0, max(4, row - 1), 12)
    detail_last_excel_row = max(5, row)
    details.print_area(0, 0, max(4, row - 1), 12)

    # Sheet: devices.
    devices_sheet = workbook.add_worksheet("Приборы")
    devices_sheet.hide_gridlines(2)
    devices_sheet.set_tab_color(colors["blue"])
    devices_sheet.merge_range("A1:G1", f"Приборы в плане — {_ru_month(plan.month)}", title_fmt)
    devices_sheet.merge_range("A2:G2", f"План №{plan.id} · ревизия {plan.revision}", subtitle_fmt)
    devices_sheet.write_row(4, 0, ["ID", "Прибор", "Модель", "Кол-во", "Версия BOM", "Спецификация", "Статус BOM"], header_fmt)
    devices_sheet.set_row(0, 32)
    devices_sheet.set_row(1, 22)
    devices_sheet.set_row(4, 34)
    devices_sheet.set_column("A:A", 8)
    devices_sheet.set_column("B:B", 36)
    devices_sheet.set_column("C:C", 20)
    devices_sheet.set_column("D:D", 14)
    devices_sheet.set_column("E:E", 13)
    devices_sheet.set_column("F:F", 26)
    devices_sheet.set_column("G:G", 14)
    devices_sheet.freeze_panes(5, 2)
    sorted_devices = sorted(devices, key=lambda item: (item.name.casefold(), item.device_id, item.bom_version))
    for index, device in enumerate(sorted_devices, start=5):
        devices_sheet.write_number(index, 0, device.device_id, id_fmt)
        devices_sheet.write(index, 1, device.name, body_fmt)
        devices_sheet.write(index, 2, device.model or "—", body_fmt)
        devices_sheet.write_number(index, 3, _decimal_number(device.qty_total), _qty_format(device.qty_total))
        devices_sheet.write_number(index, 4, device.bom_version, body_center_fmt)
        devices_sheet.write(index, 5, device.bom_name or "—", body_fmt)
        devices_sheet.write(index, 6, _status_label(device.bom_status), body_center_fmt)
        devices_sheet.set_row(index, 21)
    last_device_row = max(4, 4 + len(sorted_devices))
    if sorted_devices:
        devices_sheet.autofilter(4, 0, last_device_row, 6)
    else:
        devices_sheet.merge_range("A6:G7", "В плане нет приборов (возможны прямые позиции деталей).", note_fmt)
        last_device_row = 6
    devices_sheet.set_landscape()
    devices_sheet.fit_to_pages(1, 0)
    devices_sheet.print_area(0, 0, last_device_row, 6)

    # Sheet: invoice links.
    invoice_sheet = workbook.add_worksheet("Счета")
    invoice_sheet.hide_gridlines(2)
    invoice_sheet.set_tab_color(colors["amber_text"])
    invoice_sheet.merge_range("A1:K1", f"Покрытие плана счетами — {_ru_month(plan.month)}", title_fmt)
    invoice_sheet.merge_range("A2:K2", "Каждая строка — одна привязка счёта к детали; переносы отмечены отдельно.", subtitle_fmt)
    invoice_sheet.write_row(
        4,
        0,
        ["Группа", "ID детали", "Деталь", "Шифр", "Счёт", "Дата счёта", "Поставщик", "Покрыто", "Дата оплаты", "Оплата", "Источник"],
        header_fmt,
    )
    invoice_sheet.set_row(0, 32)
    invoice_sheet.set_row(1, 22)
    invoice_sheet.set_row(4, 38)
    invoice_sheet.set_column("A:A", 22)
    invoice_sheet.set_column("B:B", 10)
    invoice_sheet.set_column("C:C", 34)
    invoice_sheet.set_column("D:D", 22)
    invoice_sheet.set_column("E:E", 16)
    invoice_sheet.set_column("F:F", 14)
    invoice_sheet.set_column("G:G", 28)
    invoice_sheet.set_column("H:H", 14)
    invoice_sheet.set_column("I:I", 14)
    invoice_sheet.set_column("J:K", 13)
    invoice_sheet.freeze_panes(5, 2)
    sorted_invoices = sorted(
        invoices,
        key=lambda item: (
            _group_sort_key(_group_name(item.part_type)),
            item.part_name.casefold(),
            item.invoice_date,
            item.invoice_no.casefold(),
        ),
    )
    for index, invoice in enumerate(sorted_invoices, start=5):
        invoice_sheet.write(index, 0, _group_name(invoice.part_type), body_fmt)
        invoice_sheet.write_number(index, 1, invoice.part_id, id_fmt)
        invoice_sheet.write(index, 2, invoice.part_name, body_fmt)
        invoice_sheet.write(index, 3, invoice.cipher or "—", body_fmt)
        invoice_sheet.write(index, 4, invoice.invoice_no, body_fmt)
        invoice_sheet.write(index, 5, _date_text(invoice.invoice_date), body_center_fmt)
        invoice_sheet.write(index, 6, invoice.supplier or "—", body_fmt)
        invoice_sheet.write_number(index, 7, _decimal_number(invoice.qty_covered), _qty_format(invoice.qty_covered))
        if invoice.payment_date:
            invoice_sheet.write(index, 8, _date_text(invoice.payment_date), body_center_fmt)
            invoice_sheet.write(index, 9, "Оплачен", status_ok_fmt)
        else:
            invoice_sheet.write(index, 8, "—", body_center_fmt)
            invoice_sheet.write(index, 9, "Не оплачен", status_bad_fmt)
        invoice_sheet.write(index, 10, "Перенос" if invoice.is_carryover else "Счёт месяца", status_pending_fmt if invoice.is_carryover else body_center_fmt)
        invoice_sheet.set_row(index, 21)
    last_invoice_row = max(4, 4 + len(sorted_invoices))
    if sorted_invoices:
        invoice_sheet.autofilter(4, 0, last_invoice_row, 10)
    else:
        invoice_sheet.merge_range("A6:K7", "К плану пока не привязаны счета.", note_fmt)
        last_invoice_row = 6
    invoice_sheet.set_landscape()
    invoice_sheet.fit_to_pages(1, 0)
    invoice_sheet.print_area(0, 0, last_invoice_row, 10)

    # Sheet: summary.
    summary.hide_gridlines(2)
    summary.set_tab_color(colors["navy"])
    summary.merge_range("A1:H1", f"Месячный план — {_ru_month(plan.month)}", title_fmt)
    summary.merge_range("A2:H2", "Сводка потребности, покрытия счетами и поставки", subtitle_fmt)
    summary.set_row(0, 34)
    summary.set_row(1, 22)
    summary.set_column("A:A", 18)
    summary.set_column("B:B", 20)
    summary.set_column("C:H", 16)
    summary.write("A4", "План", label_fmt)
    summary.write("B4", plan.id, value_fmt)
    summary.write("A5", "Месяц", label_fmt)
    summary.write("B5", _ru_month(plan.month).capitalize(), value_fmt)
    summary.write("A6", "Ревизия", label_fmt)
    summary.write("B6", plan.revision, value_fmt)
    summary.write("A7", "Статус", label_fmt)
    summary.write("B7", _status_label(plan.status), value_fmt)
    summary.write("A8", "Сформирован", label_fmt)
    summary.write("B8", plan.generated_at.strftime("%d.%m.%Y %H:%M"), value_fmt)
    summary.write("A9", "Автор", label_fmt)
    summary.write("B9", plan.generated_by or "—", value_fmt)

    total_devices = sum((item.qty_total for item in devices), Decimal("0"))
    total_final = sum((item.qty_final for item in parts), Decimal("0"))
    total_covered = sum((item.qty_covered for item in parts), Decimal("0"))
    total_delivered = sum((item.qty_delivered for item in parts), Decimal("0"))
    summary.merge_range("D4:E4", "Приборов, шт.", kpi_label_fmt)
    summary.merge_range("D5:E6", "", kpi_value_fmt)
    device_last_excel_row = max(6, last_device_row + 1)
    summary.write_formula("D5", f"=SUM('Приборы'!D6:D{device_last_excel_row})", _kpi_format(total_devices), _decimal_number(total_devices))
    summary.merge_range("G4:H4", "Позиций деталей", kpi_label_fmt)
    summary.merge_range("G5:H6", "", kpi_value_fmt)
    summary.write_number("G5", len(parts), kpi_value_fmt)
    summary.merge_range("D8:E8", "Итого к закупке", kpi_label_fmt)
    summary.merge_range("D9:E10", "", kpi_value_fmt)
    summary.write_formula(
        "D9",
        f'=SUMIF(\'Детали\'!B6:B{detail_last_excel_row},">0",\'Детали\'!G6:G{detail_last_excel_row})',
        _kpi_format(total_final),
        _decimal_number(total_final),
    )
    summary.merge_range("G8:H8", "Покрыто счетами", kpi_label_fmt)
    summary.merge_range("G9:H10", "", kpi_value_fmt)
    summary.write_formula(
        "G9",
        f'=SUMIF(\'Детали\'!B6:B{detail_last_excel_row},">0",\'Детали\'!H6:H{detail_last_excel_row})',
        _kpi_format(total_covered),
        _decimal_number(total_covered),
    )
    summary.merge_range("D12:E12", "Поставлено", kpi_label_fmt)
    summary.merge_range("D13:E14", "", kpi_value_fmt)
    summary.write_formula(
        "D13",
        f'=SUMIF(\'Детали\'!B6:B{detail_last_excel_row},">0",\'Детали\'!J6:J{detail_last_excel_row})',
        _kpi_format(total_delivered),
        _decimal_number(total_delivered),
    )
    summary.merge_range("G12:H12", "Групп деталей", kpi_label_fmt)
    summary.merge_range("G13:H14", "", kpi_value_fmt)
    summary.write_number("G13", len(group_names), kpi_value_fmt)

    summary.merge_range("A12:B12", "Комментарий к плану", label_fmt)
    summary.merge_range("A13:B16", plan.note or "Комментарий не указан.", note_fmt)
    summary.merge_range(
        "A18:H20",
        "Структура файла: «Детали» — закупочный план с группировкой и формулами остатков; «Приборы» — состав производственного плана; «Счета» — детализация покрытия. Значения отражают состояние системы на момент выгрузки.",
        note_fmt,
    )
    summary.set_row(17, 26)
    summary.set_row(18, 26)
    summary.set_row(19, 26)
    summary.print_area("A1:H20")
    summary.set_portrait()
    summary.fit_to_pages(1, 1)
    summary.freeze_panes(2, 0)
    summary.activate()
    summary.select()

    workbook.close()
    output.seek(0)
    return output.getvalue()
