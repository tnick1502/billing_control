from app.config import settings
from app.database import _server_timeout_statements


def test_idle_session_timeout_is_longer_than_pool_recycle():
    """Живой пул не должен попадать под серверный тайм-аут: пул пересоздаёт соединение раньше."""
    stmts = _server_timeout_statements(16)
    idle = next(s for s in stmts if "idle_session_timeout" in s)
    seconds = int(idle.split("'")[1].rstrip("s"))
    assert seconds > settings.db_pool_recycle


def test_idle_session_timeout_is_not_sent_to_old_servers():
    assert not any("idle_session_timeout" in s for s in _server_timeout_statements(13))
    assert any("idle_in_transaction_session_timeout" in s for s in _server_timeout_statements(13))


def test_auth_cache_skips_put_if_access_changed_during_db_read(monkeypatch):
    """Запрос прочитал сессию до коммита изменения — в кеш он её положить не должен."""
    from app.auth_cache import AuthCache, CachedAuth
    from app.permissions import EMPTY_POLICY

    monkeypatch.setattr(settings, "auth_cache_ttl_seconds", 30)
    cache = AuthCache()

    class U:
        id = 7
        is_active = True

    def entry():
        return CachedAuth(U(), EMPTY_POLICY, 1, None, None, None, 0.0)  # type: ignore[arg-type]

    gen = cache.generation
    cache.evict_user(7)  # параллельно поменяли пароль/роль и закоммитили
    cache.put("t", entry(), gen)
    assert cache.get("t") is None

    gen = cache.generation
    cache.put("t", entry(), gen)
    assert cache.get("t") is not None
