"""Простая защита логина от перебора паролей.

In-process (память одного воркера uvicorn). Этого достаточно для текущей схемы
развёртывания (один контейнер backend без реплик). При масштабировании на несколько
воркеров/реплик защиту нужно вынести в общий стор (Redis) — см. рекомендации.
"""

import time
from threading import Lock

from app.config import settings


class _LoginGuard:
    def __init__(self) -> None:
        # ключ -> (список меток времени неудач, метка времени окончания блокировки)
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = Lock()

    def _window_seconds(self) -> float:
        return settings.login_failure_window_minutes * 60

    def retry_after(self, key: str) -> int:
        """0 — попытка разрешена; иначе сколько секунд ждать до конца блокировки."""
        now = time.monotonic()
        with self._lock:
            until = self._locked_until.get(key)
            if until is not None and until > now:
                return max(1, int(until - now))
            if until is not None:
                # Блокировка истекла — чистим состояние.
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)
            return 0

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        window = self._window_seconds()
        with self._lock:
            fails = [t for t in self._failures.get(key, []) if now - t < window]
            fails.append(now)
            self._failures[key] = fails
            if len(fails) >= settings.login_max_failures:
                self._locked_until[key] = now + settings.login_lockout_minutes * 60
                self._failures.pop(key, None)

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


login_guard = _LoginGuard()


def client_key(ip: str | None, username: str) -> str:
    return f"{ip or '-'}|{username.strip().lower()}"
