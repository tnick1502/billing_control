import logging
import secrets
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import AuditLog, User


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

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


def employee_may_write(path: str) -> bool:
    """Сотрудник: просмотр везде + создание/правка счетов и вложений (префикс /invoices)."""
    if path in EMPLOYEE_WRITE_PATHS:
        return True
    return path == "/invoices" or path.startswith("/invoices/")


def make_token() -> str:
    return secrets.token_urlsafe(48)


def normalize_role(role: str) -> str:
    value = role.strip().lower()
    if value not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Роль должна быть admin или employee")
    return value


def action_label(method: str, path: str) -> str:
    return f"{method} {path}"


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith("/assets/")


async def user_by_token(session: AsyncSession, token: str) -> User | None:
    if not token:
        return None
    result = await session.execute(select(User).where(User.session_token == token, User.is_active.is_(True)))
    return result.scalar_one_or_none()


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

    async with async_session_maker() as session:
        user = await user_by_token(session, token)
        if not user:
            return JSONResponse(status_code=401, content={"detail": "Сессия недействительна"})

        if path.startswith("/admin") and user.role != ADMIN_ROLE:
            return JSONResponse(status_code=403, content={"detail": "Доступ только для администратора"})

        if method not in SAFE_METHODS and user.role != ADMIN_ROLE and not employee_may_write(path):
            await write_audit_log(session, user, method, path, 403, "Попытка изменения без прав администратора")
            return JSONResponse(
                status_code=403,
                content={"detail": "Это действие доступно только администратору"},
            )

        request.state.user = user
        response = await call_next(request)

        if method not in SAFE_METHODS and path != "/auth/logout":
            try:
                status = getattr(response, "status_code", None) or 200
                await write_audit_log(session, user, method, path, status)
            except Exception:
                # Счёт/файл уже закоммичены в своей сессии; не превращаем сбой аудита в 500 для клиента
                log.exception(
                    "audit_logs: не удалось записать запись аудита (%s %s); ответ клиенту без изменений",
                    method,
                    path,
                )

        return response
