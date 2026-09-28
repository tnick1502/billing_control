import re

import pytest
from fastapi.routing import APIRoute

from app.auth import is_public_path
from app.main import app
from app.permissions import (
    EMPLOYEE_PRESET,
    SECTION_KEYS,
    build_policy,
    find_rule,
    normalize_permissions,
    validate_permissions,
)


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _walk(routes, prefix=""):
    """Все APIRoute приложения. В FastAPI 0.140 подключённые роутеры лежат в app.routes как
    обёртки (_IncludedRouter) — обходим их рекурсивно, иначе тест ничего не проверяет."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix, route
            continue
        original = getattr(route, "original_router", None)
        if original is not None:
            ctx = getattr(route, "include_context", None)
            yield from _walk(original.routes, prefix + (getattr(ctx, "prefix", "") or ""))


def _api_routes():
    for prefix, route in _walk(app.routes):
        for method in route.methods:
            yield method, prefix + route.path


def test_route_walker_sees_all_endpoints():
    routes = {(m, p) for m, p in _api_routes()}
    openapi_ops = {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        for method in ops
    }
    assert len(routes) >= 80
    assert openapi_ops <= routes


def test_every_route_has_permission_rule():
    """Новый эндпоинт без правила в app/permissions.py для не-админа закрыт — ловим это в CI."""
    missing = [
        f"{method} {path}"
        for method, path in _api_routes()
        if not is_public_path(path) and find_rule(method, _concrete(path)) is None
    ]
    assert missing == [], "Добавьте правило в app/permissions.py RULES: " + ", ".join(sorted(missing))


def test_unknown_path_is_denied_for_regular_role_but_allowed_for_superuser():
    everything = build_policy("x", {k: "full" for k in SECTION_KEYS}, False)
    assert everything.check("GET", "/something-new").allowed is False
    assert build_policy("admin", {}, True).check("GET", "/something-new").allowed is True


def test_admin_area_and_db_dump_are_superuser_only():
    everything = build_policy("x", {k: "full" for k in SECTION_KEYS}, False)
    assert everything.check("GET", "/admin/users").allowed is False
    assert everything.check("GET", "/admin/roles").allowed is False
    assert everything.check("GET", "/imports/db/dump").allowed is False
    assert everything.check("GET", "/imports/bom/export").allowed is True


@pytest.mark.parametrize(
    ("method", "path", "level_needed"),
    [
        ("GET", "/parts", "view"),
        ("GET", "/parts/types", "view"),
        ("POST", "/parts", "edit"),
        ("PATCH", "/parts/1", "edit"),
        ("PATCH", "/parts/1/archive", "full"),
        ("DELETE", "/parts/1", "full"),
        ("GET", "/orders/1/items", "view"),
        ("DELETE", "/orders/1/items/2", "edit"),
        ("DELETE", "/orders/1", "full"),
        ("GET", "/devices/1/bom", "view"),
        ("DELETE", "/bom/1/items/2", "edit"),
        ("DELETE", "/bom/1", "full"),
        ("DELETE", "/invoices/1/parts/2", "full"),
        ("DELETE", "/monthly-plans/1/invoice-links/2", "edit"),
        ("DELETE", "/monthly-plans/inventory/2026-08-01", "full"),
    ],
)
def test_levels_are_ordered(method: str, path: str, level_needed: str):
    order = ["none", "view", "edit", "full"]
    section = find_rule(method, path).sections[0]
    for level in order:
        policy = build_policy("x", {section: level}, False)
        expected = order.index(level) >= order.index(level_needed)
        assert policy.check(method, path).allowed is expected, (method, path, level)


def test_devices_view_does_not_grant_bom():
    policy = build_policy("x", {"devices": "view"}, False)
    assert policy.check("GET", "/devices").allowed is True
    assert policy.check("GET", "/devices/1/bom").allowed is False


def test_dependency_reads_are_read_only_and_narrow():
    plans = build_policy("x", {"monthly_plans": "edit"}, False)
    assert plans.check("GET", "/parts").allowed is True
    assert plans.check("GET", "/devices").allowed is True
    assert plans.check("GET", "/invoices/5/files").allowed is True
    # Только чтение и только списки-справочники:
    assert plans.check("POST", "/parts").allowed is False
    assert plans.check("POST", "/invoices").allowed is False
    assert plans.check("GET", "/parts/types").allowed is False
    assert plans.check("GET", "/orders").allowed is False

    invoices = build_policy("x", {"invoices": "view"}, False)
    assert invoices.check("GET", "/monthly-plans").allowed is True
    assert invoices.check("GET", "/monthly-plans/1/parts").allowed is False
    assert invoices.check("GET", "/files/3/download").allowed is True


def test_none_level_closes_section_completely():
    policy = build_policy("x", {"statistics": "view"}, False)
    assert policy.check("GET", "/stats/orders-devices-timeseries").allowed is True
    for method, path in [("GET", "/parts"), ("GET", "/monthly-plans"), ("GET", "/invoices"), ("GET", "/files/1/download")]:
        assert policy.check(method, path).allowed is False


def test_employee_preset_matches_previous_hardcoded_rights():
    policy = build_policy("employee", EMPLOYEE_PRESET, False)
    for method, path in _api_routes():
        if is_public_path(path) or path.startswith("/auth/"):
            continue
        p = _concrete(path)
        allowed = policy.check(method, p).allowed
        # Прежняя логика: админка и импорт закрыты; чтение остального открыто;
        # запись — только планы целиком и счета без DELETE.
        if path.startswith("/admin") or path.startswith("/imports"):
            expected = False
        elif method in ("GET", "HEAD"):
            expected = True
        elif path.startswith("/monthly-plans"):
            expected = True
        elif path.startswith("/invoices"):
            expected = method != "DELETE"
        else:
            expected = False
        assert allowed is expected, (method, path)


def test_permissions_normalization_and_validation():
    assert normalize_permissions({"parts": "edit", "bogus": "full", "bom": "xxx"})["parts"] == "edit"
    normalized = normalize_permissions(None)
    assert set(normalized) == set(SECTION_KEYS) and set(normalized.values()) == {"none"}
    with pytest.raises(ValueError):
        validate_permissions({"bogus": "view"})
    with pytest.raises(ValueError):
        validate_permissions({"parts": "admin"})
