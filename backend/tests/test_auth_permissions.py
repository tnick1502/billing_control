import pytest

from app.auth import employee_may_write


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/monthly-plans"),
        ("POST", "/monthly-plans/generate"),
        ("PATCH", "/monthly-plans/12"),
        ("DELETE", "/monthly-plans/12"),
        ("PATCH", "/monthly-plans/12/parts/34"),
        ("POST", "/monthly-plans/12/parts/34/files"),
        ("DELETE", "/monthly-plans/12/parts/34/files/56"),
        ("POST", "/monthly-plans/12/invoice-links/batch"),
        ("DELETE", "/monthly-plans/12/invoice-links/78"),
        ("POST", "/monthly-plans/inventory/2026-08-01"),
        ("DELETE", "/monthly-plans/inventory/2026-08-01"),
    ],
)
def test_employee_has_full_write_access_inside_monthly_plans(method: str, path: str):
    assert employee_may_write(method, path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/parts/1",
        "/devices/1/bom",
        "/bom/1/items",
        "/orders/1",
    ],
)
def test_employee_still_cannot_modify_production_reference_data_or_orders(path: str):
    assert employee_may_write("PATCH", path) is False


def test_employee_cannot_delete_invoice_directly():
    assert employee_may_write("DELETE", "/invoices/1") is False
    assert employee_may_write("DELETE", "/invoices/1/parts/2") is False
