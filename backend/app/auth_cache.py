"""TTL-кеш авторизации в памяти процесса: хэш токена → (пользователь, политика, сессия).

Кешируется ТОЛЬКО ответ на вопрос «кто пользователь и что ему можно». Данные приложения
(планы, счета, детали…) не кешируются никогда.

Включается ``AUTH_CACHE_TTL_SECONDS`` > 0 (0 — выключено, поведение как без кеша).

Любое изменение, влияющее на доступ, делается через API и сразу вытесняет записи:
выход, смена пароля/роли/активности/логина, удаление пользователя, правка/удаление роли.
Процесс backend один (uvicorn без --workers), поэтому вытеснение точное и мгновенное.
При нескольких процессах чужие процессы увидят изменение не позже чем через TTL.

Гонка «запрос прочитал старые данные до коммита изменения и положил их в кеш уже после
вытеснения» закрыта двумя мерами: вытеснение делается ПОСЛЕ коммита, а каждое вытеснение
увеличивает ``generation`` — запись, прочитанная до этого, в кеш не попадёт (``put`` сверяет
поколение, снятое перед чтением из БД).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from app.config import settings
from app.permissions import Policy


@dataclass
class CachedAuth:
    user: Any              # отсоединённый снимок User (expire_on_commit=False); только чтение
    policy: Policy
    session_id: int
    expires_at: datetime
    last_used_at: datetime
    role_name: str | None
    cached_at: float


class AuthCache:
    def __init__(self) -> None:
        self._data: OrderedDict[str, CachedAuth] = OrderedDict()
        self._lock = Lock()
        self._generation = 0

    @property
    def generation(self) -> int:
        """Снять ДО чтения сессии из БД и передать в ``put``."""
        return self._generation

    @property
    def enabled(self) -> bool:
        return settings.auth_cache_ttl_seconds > 0

    def get(self, token_hash: str) -> CachedAuth | None:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(token_hash)
            if entry is None:
                return None
            if now - entry.cached_at >= settings.auth_cache_ttl_seconds:
                self._data.pop(token_hash, None)
                return None
            self._data.move_to_end(token_hash)
            return entry

    def put(self, token_hash: str, entry: CachedAuth, generation: int) -> None:
        if not self.enabled:
            return
        entry.cached_at = time.monotonic()
        with self._lock:
            if generation != self._generation:
                # Пока мы читали из БД, доступ кому-то меняли — не кешируем возможно устаревшее.
                return
            self._data[token_hash] = entry
            self._data.move_to_end(token_hash)
            while len(self._data) > settings.auth_cache_max_entries:
                self._data.popitem(last=False)

    def evict_token(self, token_hash: str) -> None:
        with self._lock:
            self._generation += 1
            self._data.pop(token_hash, None)

    def evict_user(self, user_id: int) -> None:
        with self._lock:
            self._generation += 1
            for key in [k for k, v in self._data.items() if getattr(v.user, "id", None) == user_id]:
                self._data.pop(key, None)

    def evict_role(self, role_code: str) -> None:
        with self._lock:
            self._generation += 1
            for key in [k for k, v in self._data.items() if v.policy.role_code == role_code]:
                self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


auth_cache = AuthCache()
