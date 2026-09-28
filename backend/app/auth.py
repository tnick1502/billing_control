import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
import bcrypt
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_cache import CachedAuth, auth_cache
from app.config import settings
from app.database import async_session_maker
from app.models import AuditLog, Role, User, UserSession
from app.permissions import (
    ADMIN_ROLE,
    EMPLOYEE_PRESET,
    EMPLOYEE_ROLE,
    EMPTY_POLICY,
    Policy,
    build_policy,
    normalize_permissions,
    policy_cache,
)

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


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATHS = {
    "/health",
    "/auth/login",
    "/docs",
    "/redoc",
    "/openapi.json",
}

log = logging.getLogger(__name__)


_EMPLOYEE_PRESET_POLICY = build_policy(EMPLOYEE_ROLE, EMPLOYEE_PRESET, False)


def employee_may_write(method: str, path: str) -> bool:
    """Совместимость: права пресета «Сотрудник» на изменение данных.

    Раньше это была единственная логика прав. Теперь права задаются ролями
    (``app.permissions``); функция проверяет, что пресет роли ``employee`` даёт ровно
    прежнее поведение: планы — всё, счета — всё кроме удаления, остальное — только чтение.
    """
    return _EMPLOYEE_PRESET_POLICY.check(method, path).allowed


def make_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """В БД храним только SHA-256 хэш токена (токен высокоэнтропийный, соль не нужна)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def resolve_role(session: AsyncSession, code: str) -> Role:
    """Найти роль по коду; 400, если такой роли нет."""
    value = (code or "").strip()
    role = await session.scalar(select(Role).where(Role.code == value)) if value else None
    if role is None:
        raise HTTPException(status_code=400, detail="Роль не найдена")
    return role


def policy_for(user: User, role: Role | None) -> Policy:
    if role is None:
        # Не должно случаться (FK users.role → roles.code). Админа при этом не запираем.
        if user.role == ADMIN_ROLE:
            return build_policy(ADMIN_ROLE, {}, True)
        return EMPTY_POLICY
    return policy_cache.get(role.code, role.revision, role.permissions, role.is_superuser)


async def warn_if_no_active_admins() -> None:
    """Громкое предупреждение в лог, если в системе не осталось активных администраторов."""
    async with async_session_maker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(User)
            .join(Role, Role.code == User.role)
            .where(Role.is_superuser.is_(True), User.is_active.is_(True))
        )
    if not count:
        log.error(
            "НЕТ АКТИВНЫХ АДМИНИСТРАТОРОВ: админ-панель недоступна. Восстановление: "
            "UPDATE users SET role = 'admin', is_active = true WHERE username = '<логин>';"
        )


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
    """Удалить сессию и СРАЗУ закоммитить, затем вытеснить токен из кеша авторизации.

    Порядок важен: вытеснение до коммита позволило бы параллельному запросу снова
    положить в кеш ещё не удалённую сессию.
    """
    if not token:
        return
    await session.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    await session.commit()
    auth_cache.evict_token(hash_token(token))


async def _resolve_session(
    session: AsyncSession, token: str
) -> tuple[User, UserSession, Role | None] | None:
    """Вернуть (user, session, role) по валидному непросроченному токену активного пользователя.

    Один SELECT: сессия + пользователь + роль (JOIN по уникальному roles.code) —
    права приходят тем же запросом, без дополнительных обращений к БД.
    """
    if not token:
        return None
    row = await session.execute(
        select(UserSession, User, Role)
        .join(User, User.id == UserSession.user_id)
        .outerjoin(Role, Role.code == User.role)
        .where(UserSession.token_hash == hash_token(token))
    )
    found = row.first()
    if not found:
        return None
    user_session, user, role = found
    if not user.is_active:
        return None
    if _aware(user_session.expires_at) <= _now():
        # Просрочена — считаем недействительной. Строку не удаляем здесь (это была бы запись
        # на горячем пути); просроченные сессии подчищаются при логине/логауте и фоном.
        return None
    return user, user_session, role


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _renew_due(last_used_at: datetime) -> bool:
    return (_now() - _aware(last_used_at)) >= timedelta(minutes=settings.session_idle_renew_minutes)


async def _maybe_renew(session: AsyncSession, user_session: UserSession) -> bool:
    """Скользящее продление. Возвращает True, только если реально продлили (и тогда нужен commit).

    На горячем пути (каждый запрос) НИЧЕГО не пишем: запись в БД делается не чаще порога
    ``session_idle_renew_minutes`` — иначе на удалённой БД каждый запрос тормозит из-за коммита.
    """
    if not _renew_due(user_session.last_used_at):
        return False
    now = _now()
    user_session.last_used_at = now
    user_session.expires_at = now + timedelta(hours=settings.session_ttl_hours)
    await session.commit()
    return True


async def _maybe_renew_cached(entry: CachedAuth) -> None:
    """То же продление для записи из кеша: точечный UPDATE по id, не чаще порога."""
    if not _renew_due(entry.last_used_at):
        return
    now = _now()
    expires = now + timedelta(hours=settings.session_ttl_hours)
    # Сначала двигаем метку в кеше — параллельные запросы не будут писать повторно.
    entry.last_used_at = now
    entry.expires_at = expires
    async with async_session_maker() as session:
        await session.execute(
            update(UserSession)
            .where(UserSession.id == entry.session_id)
            .values(last_used_at=now, expires_at=expires)
        )
        await session.commit()


async def ensure_default_roles() -> None:
    """Засеять системные роли и привести БД к инварианту «у каждого users.role есть роль».

    Идемпотентно. Вызывается при старте ДО ``ensure_default_users`` и до создания FK.
    """
    async with async_session_maker() as session:
        roles = {r.code: r for r in (await session.execute(select(Role))).scalars().all()}
        changed = False
        admin = roles.get(ADMIN_ROLE)
        if admin is None:
            session.add(
                Role(
                    code=ADMIN_ROLE,
                    name="Администратор",
                    description="Системная роль: полный доступ, управление пользователями и ролями",
                    is_system=True,
                    is_superuser=True,
                    permissions={},
                )
            )
            changed = True
        elif not (admin.is_system and admin.is_superuser):
            admin.is_system = True
            admin.is_superuser = True
            admin.revision = (admin.revision or 0) + 1
            changed = True
        # «Сотрудник» — обычная роль: её можно изменить и удалить. Засеваем только при первой
        # инициализации (таблица ролей пуста), чтобы удалённая админом роль не «воскресала».
        if not roles:
            session.add(
                Role(
                    code=EMPLOYEE_ROLE,
                    name="Сотрудник",
                    description="Планы — полностью, счета — без удаления, остальное — просмотр",
                    permissions=dict(EMPLOYEE_PRESET),
                )
            )
            changed = True
        # Страховка: коды ролей у пользователей, которых нет в roles (FK иначе не создать).
        known = set(roles) | {ADMIN_ROLE} | ({EMPLOYEE_ROLE} if not roles else set())
        orphan_codes = (
            await session.execute(select(User.role).distinct().where(User.role.not_in(known)))
        ).scalars().all()
        for code in orphan_codes:
            log.warning("roles: у пользователей найдена неизвестная роль %r — создана роль без прав", code)
            session.add(Role(code=code, name=f"Роль {code}", permissions=normalize_permissions({})))
            changed = True
        if changed:
            await session.commit()


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


def get_policy(request: Request) -> Policy:
    return getattr(request.state, "policy", None) or EMPTY_POLICY


async def require_admin(request: Request) -> User:
    user = await get_current_user(request)
    if not get_policy(request).is_superuser:
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


async def _authenticate(token: str) -> tuple[User, Policy, str | None] | None:
    """Кто пользователь и что ему можно. Из кеша (если включён) или одним SELECT из БД."""
    token_hash = hash_token(token)
    cached = auth_cache.get(token_hash)
    if cached is not None:
        if _aware(cached.expires_at) <= _now() or not cached.user.is_active:
            auth_cache.evict_token(token_hash)
            return None
        await _maybe_renew_cached(cached)
        return cached.user, cached.policy, cached.role_name

    generation = auth_cache.generation  # до чтения из БД — см. AuthCache.put
    # Короткая сессия: один SELECT и сразу освобождаем соединение в пул ДО выполнения
    # хендлера (который откроет своё соединение). Иначе на удалённой БД каждое соединение
    # держится весь запрос → пул быстро исчерпывается.
    async with async_session_maker() as session:
        resolved = await _resolve_session(session, token)
        if not resolved:
            return None
        user, user_session, role = resolved
        policy = policy_for(user, role)
        role_name = role.name if role is not None else user.role
        # Запись в БД только если реально пора продлить сессию (не на каждом запросе).
        await _maybe_renew(session, user_session)
        auth_cache.put(
            token_hash,
            CachedAuth(
                user=user,
                policy=policy,
                session_id=user_session.id,
                expires_at=user_session.expires_at,
                last_used_at=user_session.last_used_at,
                role_name=role_name,
                cached_at=0.0,
            ),
            generation,
        )
    # Соединение возвращено в пул здесь. user остаётся пригоден (expire_on_commit=False).
    return user, policy, role_name


async def auth_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path
    method = request.method.upper()

    if method == "OPTIONS" or is_public_path(path):
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return JSONResponse(status_code=401, content={"detail": "Требуется авторизация"})

    authenticated = await _authenticate(token)
    if not authenticated:
        return JSONResponse(status_code=401, content={"detail": "Сессия недействительна"})
    user, policy, role_name = authenticated

    decision = policy.check(method, path)
    if not decision.allowed:
        if method not in SAFE_METHODS:
            try:
                async with async_session_maker() as audit_session:
                    await write_audit_log(audit_session, user, method, path, 403, f"Отказано: {decision.reason}")
            except Exception:
                log.exception("audit_logs: не удалось записать отказ (%s %s)", method, path)
        return JSONResponse(status_code=403, content={"detail": decision.reason or "Нет доступа"})

    request.state.user = user
    request.state.policy = policy
    request.state.role_name = role_name
    request.state.session_token = token
    response = await call_next(request)

    if method not in SAFE_METHODS and path != "/auth/logout":
        try:
            status = getattr(response, "status_code", None) or 200
            async with async_session_maker() as audit_session:
                await write_audit_log(
                    audit_session, user, method, path, status, getattr(request.state, "audit_details", None)
                )
        except Exception:
            # Счёт/файл уже закоммичены в своей сессии; не превращаем сбой аудита в 500 для клиента
            log.exception(
                "audit_logs: не удалось записать запись аудита (%s %s); ответ клиенту без изменений",
                method,
                path,
            )

    return response
