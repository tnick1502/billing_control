import asyncio
from types import SimpleNamespace

import pytest

import app.schema_ensure as schema_ensure


def test_fk_lock_timeout_stops_startup(monkeypatch):
    class Result:
        def scalar_one_or_none(self):
            return None

    class Connection:
        async def execute(self, statement):
            sql = str(statement)
            if "ADD CONSTRAINT fk_users_role_roles" in sql:
                raise TimeoutError("lock timeout")
            return Result()

    class Transaction:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(
        schema_ensure,
        "engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), begin=Transaction),
    )

    with pytest.raises(RuntimeError, match="не создан или не проверен"):
        asyncio.run(schema_ensure.ensure_users_role_fk())


def test_preflight_stops_before_discarding_legacy_data():
    class Result:
        def all(self):
            return [("users", "session_token")]

    class Connection:
        async def execute(self, _statement):
            return Result()

    with pytest.raises(RuntimeError, match="users.session_token"):
        asyncio.run(schema_ensure._preflight_legacy_schema(Connection()))
