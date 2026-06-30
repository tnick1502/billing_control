import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_maker
from app.models import AuditLog, User, UserSession

# bcrypt не принимает пароли длиннее 72 байт (молча усекает либо падает в новых версиях).
_BCRYPT_MAX_BYTES = 72


def _bcrypt_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(plain), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_bytes(plain), hashed.encode())
    except ValueError:
        # Битый/нестандартный хэш в БД — считаем пароль неверным, а не падаем в 500.
        return False


ADMIN_ROLE = "admin"
EMPLOYEE_ROLE = "employee"
VALID_ROLES = {ADMIN_ROLE, EMPLOYEE_ROLE}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
EMPLOYEE_WRITE_PATHS = {"/auth/logout"}
PUBLIC_PATHS = {
    "/health",
    "/auth/login",
    "/docs",
    "/redoc",
    "/openapi.json",
}

log = logging.getLogger(__name__)


def employee_may_write(method: str, path: str) -> bool:
    """Права сотрудника на изменение данных.

    Сотрудник может создавать/редактировать счета и вложения (префикс ``/invoices``),
    но НЕ удалять их — удаление финансовых документов и привязок доступно только админу.
    """
    if path in EMPLOYEE_WRITE_PATHS:
        return True
    is_invoices = path == "/invoices" or path.startswith("/invoices/")
    if not is_invoices:
        return False
    return method.upper() != "DELETE"


def make_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """В БД храним только SHA-256 хэш токена (токен высокоэнтропийный, соль не нужна)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_role(role: str) -> str:
    value = role.strip().lower()
    if value not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Роль должна быть admin или employee")
    return value


def action_label(method: str, path: str) -> str:
    return f"{method} {path}"


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/assets/")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_session(session: AsyncSession, user: User) -> str:
    """Создать новую сессию для пользователя и вернуть сырой токен (в БД — только хэш)."""
    token = make_token()
    ttl = timedelta(hours=settings.session_ttl_hours)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_now() + ttl,
        )
    )
    await session.flush()
    return token


async def delete_session_by_token(session: AsyncSession, token: str) -> None:
    if not token:
        return
    await session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))


async def _resolve_session(session: AsyncSession, token: str) -> tuple[User, UserSession] | None:
    """Вернуть (user, session) по валидному непросроченному токену активного пользователя."""
    if not token:
        return None
    row = await session.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token))
    )
    found = row.first()
    if not found:
        return None
    user_session, user = found
    if not user.is_active:
        return None
    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now():
        # Просрочена — считаем недействительной. Строку не удаляем здесь (это была бы запись
        # на горячем пути); просроченные сессии подчищаются при логине/логауте и фоном.
        return None
    return user, user_session


async def _maybe_renew(session: AsyncSession, user_session: UserSession) -> bool:
    """Скользящее продление. Возвращает True, только если реально продлили (и тогда нужен commit).

    На горячем пути (каждый запрос) НИЧЕГО не пишем: запись в БД делается не чаще порога
    ``session_idle_renew_minutes`` — иначе на удалённой БД каждый запрос тормозит из-за коммита.
    """
    now = _now()
    last_used = user_session.last_used_at
    if last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=timezone.utc)
    if (now - last_used) < timedelta(minutes=settings.session_idle_renew_minutes):
        return False
    user_session.last_used_at = now
    user_session.expires_at = now + timedelta(hours=settings.session_ttl_hours)
    await session.commit()
    return True


async def ensure_default_users() -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        if not users:
            session.add_all(
                [
                    User(username="admin", password=hash_password("admin"), full_name="Администратор", role=ADMIN_ROLE, is_active=True),
                    User(username="employee", password=hash_password("employee"), full_name="Сотрудник", role=EMPLOYEE_ROLE, is_active=True),
                ]
            )
            await session.commit()
            return
        # Migrate any plain-text passwords to bcrypt
        migrated = False
        for user in users:
            if not user.password.startswith("$2"):
                user.password = hash_password(user.password)
                migrated = True
        if migrated:
            await session.commit()


async def get_current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user


async def require_admin(request: Request) -> User:
    user = await get_current_user(request)
    if user.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return user


async def write_audit_log(
    session: AsyncSession,
    user: User | None,
    method: str,
    path: str,
    status_code: int | None,
    details: str | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            role=user.role if user else None,
            action=action_label(method, path),
            method=method,
            path=path,
            status_code=status_code,
            details=details,
        )
    )
    await session.commit()


async def auth_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path
    method = request.method.upper()

    if method == "OPTIONS" or is_public_path(path):
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return JSONResponse(status_code=401, content={"detail": "Требуется авторизация"})

    # Авторизация — короткая сессия: один SELECT и сразу освобождаем соединение в пул
    # ДО выполнения хендлера (который откроет своё соединение). Иначе на удалённой БД
    # каждое соединение держится весь запрос → пул быстро исчерпывается, отсюда тормоза и сбросы.
    async with async_session_maker() as session:
        resolved = await _resolve_session(session, token)
        if not resolved:
            return JSONResponse(status_code=401, content={"detail": "Сессия недействительна"})
        user, user_session = resolved

        if path.startswith("/admin") and user.role != ADMIN_ROLE:
            return JSONResponse(status_code=403, content={"detail": "Доступ только для администратора"})

        if method not in SAFE_METHODS and user.role != ADMIN_ROLE and not employee_may_write(method, path):
            await write_audit_log(session, user, method, path, 403, "Попытка изменения без прав администратора")
            return JSONResponse(
                status_code=403,
                content={"detail": "Это действие доступно только администратору"},
            )

        # Запись в БД только если реально пора продлить сессию (не на каждом запросе).
        await _maybe_renew(session, user_session)
    # Соединение возвращено в пул здесь. user остаётся пригоден (expire_on_commit=False).

    request.state.user = user
    request.state.session_token = token
    response = await call_next(request)

    if method not in SAFE_METHODS and path != "/auth/logout":
        try:
            status = getattr(response, "status_code", None) or 200
            async with async_session_maker() as audit_session:
                await write_audit_log(audit_session, user, method, path, status)
        except Exception:
            # Счёт/файл уже закоммичены в своей сессии; не превращаем сбой аудита в 500 для клиента
            log.exception(
                "audit_logs: не удалось записать запись аудита (%s %s); ответ клиенту без изменений",
                method,
                path,
            )

    return response
