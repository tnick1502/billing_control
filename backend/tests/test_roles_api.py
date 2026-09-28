"""Сквозные проверки ролей и прав через HTTP (ASGI) на SQLite в памяти."""

import asyncio

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.auth as auth_module
import app.database as database_module
from app.auth import ensure_default_roles, ensure_default_users
from app.auth_cache import auth_cache
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.permissions import policy_cache


@pytest.fixture()
def client(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(auth_module, "async_session_maker", maker)
    monkeypatch.setattr(database_module, "async_session_maker", maker)

    async def _get_db():
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db
    auth_cache.clear()
    policy_cache.clear()

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_default_roles()
        await ensure_default_users()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(setup())

    class Client:
        def __init__(self):
            self._c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

        def request(self, method, url, token=None, **kw):
            headers = kw.pop("headers", {})
            if token:
                headers["Authorization"] = f"Bearer {token}"
            return loop.run_until_complete(self._c.request(method, url, headers=headers, **kw))

        def login(self, username, password):
            r = self.request("POST", "/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
            return r.json()["token"]

    c = Client()
    yield c
    loop.run_until_complete(c._c.aclose())
    loop.run_until_complete(engine.dispose())
    loop.close()
    app.dependency_overrides.clear()
    auth_cache.clear()


def _users(client, token):
    return {u["username"]: u for u in client.request("GET", "/admin/users", token).json()}


def test_seeded_roles_and_me_payload(client):
    admin = client.login("admin", "admin")
    me = client.request("GET", "/auth/me", admin).json()
    assert me["is_superuser"] is True and me["role_name"] == "Администратор"
    assert set(me["permissions"].values()) == {"full"}

    emp = client.login("employee", "employee")
    me = client.request("GET", "/auth/me", emp).json()
    assert me["is_superuser"] is False
    assert me["permissions"]["monthly_plans"] == "full"
    assert me["permissions"]["invoices"] == "edit"
    assert me["permissions"]["import"] == "none"

    roles = client.request("GET", "/admin/roles", admin).json()
    by_code = {r["code"]: r for r in roles}
    assert by_code["admin"]["is_system"] and by_code["admin"]["users_count"] == 1
    assert by_code["employee"]["users_count"] == 1


def test_employee_keeps_previous_rights_over_http(client):
    emp = client.login("employee", "employee")
    assert client.request("GET", "/admin/users", emp).status_code == 403
    assert client.request("POST", "/parts", emp, json={"name": "x"}).status_code == 403
    assert client.request("DELETE", "/invoices/1", emp).status_code == 403
    assert client.request("POST", "/imports/bom", emp).status_code == 403


def test_system_role_is_protected(client):
    admin = client.login("admin", "admin")
    admin_role = next(r for r in client.request("GET", "/admin/roles", admin).json() if r["code"] == "admin")
    assert client.request("PATCH", f"/admin/roles/{admin_role['id']}", admin, json={"name": "X"}).status_code == 403
    assert client.request("DELETE", f"/admin/roles/{admin_role['id']}", admin).status_code == 403
    assert client.request("POST", f"/admin/roles/{admin_role['id']}/copy", admin).status_code == 400


def test_custom_role_lifecycle_and_immediate_effect(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_cache_ttl_seconds", 30)  # и с включённым кешем права применяются сразу
    admin = client.login("admin", "admin")

    r = client.request("POST", "/admin/roles", admin, json={"name": "Аналитик", "permissions": {"statistics": "view"}})
    assert r.status_code == 200, r.text
    role = r.json()
    assert role["code"].startswith("r_") and role["permissions"]["parts"] == "none"
    assert client.request("POST", "/admin/roles", admin, json={"name": "аналитик"}).status_code == 409
    assert client.request("POST", "/admin/roles", admin, json={"name": "Y", "permissions": {"bogus": "view"}}).status_code == 422

    r = client.request(
        "POST", "/admin/users", admin,
        json={"username": "ana", "password": "secret1", "role": role["code"], "is_active": True},
    )
    assert r.status_code == 200 and r.json()["role_name"] == "Аналитик"
    ana = client.login("ana", "secret1")
    assert client.request("GET", "/parts", ana).status_code == 403
    assert client.request("GET", "/auth/me", ana).json()["permissions"]["statistics"] == "view"

    # Права поменяли — действуют со следующего запроса, без перелогина.
    r = client.request(
        "PATCH", f"/admin/roles/{role['id']}", admin,
        json={"permissions": {"statistics": "view", "parts": "view"}, "revision": role["revision"]},
    )
    assert r.status_code == 200, r.text
    assert client.request("GET", "/parts", ana).status_code == 200
    # Устаревшая ревизия — конфликт (две вкладки админа).
    stale = client.request("PATCH", f"/admin/roles/{role['id']}", admin, json={"name": "Z", "revision": role["revision"]})
    assert stale.status_code == 409

    # Роль с пользователями удалить нельзя.
    r = client.request("DELETE", f"/admin/roles/{role['id']}", admin)
    assert r.status_code == 409 and "ana" in r.json()["detail"]

    uid = _users(client, admin)["ana"]["id"]
    assert client.request("PATCH", f"/admin/users/{uid}", admin, json={"role": "employee"}).status_code == 200
    assert client.request("DELETE", f"/admin/roles/{role['id']}", admin).status_code == 204

    # Журнал содержит подробности.
    logs = client.request("GET", "/admin/audit-logs", admin).json()
    assert any("Статистика" in (l["details"] or "") or "Аналитик" in (l["details"] or "") for l in logs)


def test_cache_is_evicted_on_password_change_and_deactivation(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_cache_ttl_seconds", 30)
    admin = client.login("admin", "admin")
    emp = client.login("employee", "employee")
    assert client.request("GET", "/auth/me", emp).status_code == 200  # попал в кеш
    uid = _users(client, admin)["employee"]["id"]

    assert client.request("PATCH", f"/admin/users/{uid}", admin, json={"password": "employee1300767"}).status_code == 200
    assert client.request("GET", "/auth/me", emp).status_code == 401

    emp2 = client.login("employee", "employee1300767")
    assert client.request("GET", "/auth/me", emp2).status_code == 200
    assert client.request("PATCH", f"/admin/users/{uid}", admin, json={"is_active": False}).status_code == 200
    assert client.request("GET", "/auth/me", emp2).status_code == 401

    # Выход тоже сразу убирает токен из кеша.
    assert client.request("POST", "/auth/logout", admin).status_code == 204
    assert client.request("GET", "/auth/me", admin).status_code == 401


def test_admin_cannot_lock_the_system(client):
    admin = client.login("admin", "admin")
    admin_id = _users(client, admin)["admin"]["id"]
    assert client.request("PATCH", f"/admin/users/{admin_id}", admin, json={"role": "employee"}).status_code == 400
    assert client.request("PATCH", f"/admin/users/{admin_id}", admin, json={"is_active": False}).status_code == 400
    assert client.request("DELETE", f"/admin/users/{admin_id}", admin).status_code == 400

    # Второй админ может понизить первого, но не последнего активного.
    r = client.request(
        "POST", "/admin/users", admin,
        json={"username": "boss", "password": "secret1", "role": "admin", "is_active": True},
    )
    boss_id = r.json()["id"]
    boss = client.login("boss", "secret1")
    assert client.request("PATCH", f"/admin/users/{admin_id}", boss, json={"role": "employee"}).status_code == 200
    # admin теперь сотрудник: админка закрыта сразу
    assert client.request("GET", "/admin/users", admin).status_code == 403
    # boss — последний активный админ: деактивировать/удалить себя нельзя, и другим тоже
    assert client.request("PATCH", f"/admin/users/{boss_id}", boss, json={"is_active": False}).status_code == 400
    assert client.request("PATCH", f"/admin/users/{admin_id}", boss, json={"role": "nope"}).status_code == 400


def test_role_sections_and_db_status_are_admin_only(client):
    admin = client.login("admin", "admin")
    emp = client.login("employee", "employee")
    sections = client.request("GET", "/admin/roles/sections", admin).json()
    assert [l["key"] for l in sections["levels"]] == ["none", "view", "edit", "full"]
    assert client.request("GET", "/admin/roles/sections", emp).status_code == 403
    assert client.request("GET", "/admin/db-status", emp).status_code == 403


def test_deleted_employee_role_is_not_recreated_on_restart(client):
    admin = client.login("admin", "admin")
    uid = _users(client, admin)["employee"]["id"]
    assert client.request("DELETE", f"/admin/users/{uid}", admin).status_code == 204
    emp_role = next(r for r in client.request("GET", "/admin/roles", admin).json() if r["code"] == "employee")
    assert client.request("DELETE", f"/admin/roles/{emp_role['id']}", admin).status_code == 204

    loop = asyncio.new_event_loop()
    loop.run_until_complete(ensure_default_roles())
    loop.close()
    codes = [r["code"] for r in client.request("GET", "/admin/roles", admin).json()]
    assert codes == ["admin"]
