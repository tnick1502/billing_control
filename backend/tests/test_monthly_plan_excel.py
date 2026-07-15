from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from app.services.monthly_plan_excel import (
    PlanDeviceExportRow,
    PlanExportMeta,
    PlanInvoiceExportRow,
    PlanPartExportRow,
    build_monthly_plan_xlsx,
)


class MonthlyPlanExcelTest(unittest.TestCase):
    def test_workbook_contains_expected_sheets_groups_and_formulas(self) -> None:
        payload = build_monthly_plan_xlsx(
            PlanExportMeta(
                id=7,
                month=date(2026, 7, 1),
                revision=2,
                status="draft",
                generated_at=datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc),
                generated_by="test",
                note="Проверка выгрузки",
            ),
            [
                PlanDeviceExportRow(
                    device_id=4,
                    name="ЛИГА КЛ1",
                    model="100 кН",
                    qty_total=Decimal("2"),
                    bom_version=3,
                    bom_name="Основная",
                    bom_status="active",
                )
            ],
            [
                PlanPartExportRow(
                    part_id=11,
                    name="Корпус",
                    cipher="PG.01.00.001",
                    article="A-100",
                    part_type="Изготавливаемые детали",
                    qty_required=Decimal("4"),
                    qty_final=Decimal("5"),
                    qty_covered=Decimal("3"),
                    qty_delivered=Decimal("2"),
                ),
                PlanPartExportRow(
                    part_id=12,
                    name="Болт М8",
                    cipher=None,
                    article=None,
                    part_type="Крепеж",
                    qty_required=Decimal("16"),
                    qty_final=Decimal("16"),
                    qty_covered=Decimal("16"),
                    qty_delivered=Decimal("16"),
                ),
            ],
            [
                PlanInvoiceExportRow(
                    part_id=11,
                    part_name="Корпус",
                    cipher="PG.01.00.001",
                    part_type="Изготавливаемые детали",
                    invoice_no="СФ-42",
                    invoice_date=date(2026, 7, 10),
                    supplier="ООО Поставщик",
                    qty_covered=Decimal("3"),
                    payment_date=None,
                    is_carryover=False,
                )
            ],
        )

        self.assertGreater(len(payload), 10_000)
        with ZipFile(BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/worksheets/sheet1.xml", names)
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertLess(workbook_xml.index('name="Сводка"'), workbook_xml.index('name="Детали"'))
            self.assertIn('name="Приборы"', workbook_xml)
            self.assertIn('name="Счета"', workbook_xml)
            shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
            self.assertIn("Изготавливаемые детали", shared_strings)
            self.assertIn("PG.01.00.001", shared_strings)
            all_sheets_xml = "".join(
                archive.read(name).decode("utf-8")
                for name in names
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            self.assertIn("MAX(G", all_sheets_xml)
            self.assertIn("SUMIF", all_sheets_xml)

    def test_fractional_quantities_use_decimal_number_format(self) -> None:
        """Дробные количества не должны визуально округляться до целых (формат #,##0.00)."""
        payload = build_monthly_plan_xlsx(
            PlanExportMeta(
                id=1,
                month=date(2026, 7, 1),
                revision=1,
                status="draft",
                generated_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
                generated_by=None,
                note=None,
            ),
            [],
            [
                PlanPartExportRow(
                    part_id=1,
                    name="Кабель",
                    cipher=None,
                    article=None,
                    part_type="Материалы",
                    qty_required=Decimal("4.25"),
                    qty_final=Decimal("5.5"),
                    qty_covered=Decimal("3"),
                    qty_delivered=Decimal("0"),
                )
            ],
            [],
        )
        with ZipFile(BytesIO(payload)) as archive:
            styles = archive.read("xl/styles.xml").decode("utf-8")
            self.assertIn("#,##0.00", styles)


if __name__ == "__main__":
    unittest.main()
