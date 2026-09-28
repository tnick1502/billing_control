import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_session,
    delete_session_by_token,
    get_policy,
    hash_password,
    policy_for,
    require_admin,
    resolve_role,
    verify_password,
    write_audit_log,
)
from app.auth_cache import auth_cache
from app.config import settings
from app.database import db_server_status, get_db, pool_snapshot
from app.login_guard import client_key, login_guard
from app.models import AuditLog, Role, User, UserSession
from app.permissions import (
    LEVEL_HINTS,
    LEVEL_LABELS,
    LEVELS,
    SECTIONS,
    normalize_permissions,
    policy_cache,
    validate_permissions,
)
from app.schemas.common import (
    AuditLogRead,
    AuthToken,
    MeRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserCreate,
    UserListRead,
    UserLogin,
    UserUpdate,
)

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _me_payload(user: User, role: Role | None) -> dict:
    policy = policy_for(user, role)
    return {
        **UserListRead.model_validate(user).model_dump(),
        "role_name": role.name if role is not None else user.role,
        "is_superuser": policy.is_superuser,
        "permissions": policy.permissions(),
    }


def _set_audit(request: Request, details: str) -> None:
    """Подробности для записи аудита, которую middleware делает после ответа."""
    request.state.audit_details = details[:4000]


# --- Вход / выход / текущий пользователь ------------------------------------------------


@router.post("/auth/login", response_model=AuthToken)
async def login(data: UserLogin, request: Request, session: AsyncSession = Depends(get_db, scope="function")):
    key = client_key(_client_ip(request), data.username)
    retry_after = login_guard.retry_after(key)
    if retry_after:
        await write_audit_log(session, None, "POST", "/auth/login", 429, f"Блокировка перебора: {data.username}")
        raise HTTPException(
            status_code=429,
            detail="Слишком много неудачных попыток входа. Повторите позже.",
            headers={"Retry-After": str(retry_after)},
        )

    result = await session.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(data.password, user.password):
        login_guard.record_failure(key)
        await write_audit_log(session, user, "POST", "/auth/login", 401, f"Неуспешный вход: {data.username}")
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    login_guard.record_success(key)
    token = await create_session(session, user)
    await session.refresh(user)
    role = await session.scalar(select(Role).where(Role.code == user.role))
    await write_audit_log(session, user, "POST", "/auth/login", 200, "Вход в систему")
    return {"token": token, "user": _me_payload(user, role)}


@router.get("/auth/me", response_model=MeRead)
async def me(request: Request):
    # Права уже получены middleware тем же SELECT, что и сессия, — БД здесь не нужна.
    user: User = request.state.user
    policy = get_policy(request)
    return {
        **UserListRead.model_validate(user).model_dump(),
        "role_name": getattr(request.state, "role_name", None) or user.role,
        "is_superuser": policy.is_superuser,
        "permissions": policy.permissions(),
    }


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, session: AsyncSession = Depends(get_db, scope="function")):
    token = getattr(request.state, "session_token", "")
    await delete_session_by_token(session, token)
    return None


# --- Пользователи ---------------------------------------------------------------------


async def _count_other_active_superusers(session: AsyncSession, exclude_user_id: int) -> int:
    """Сколько ещё активных админов, кроме указанного.

    Строки суперпользовательских ролей блокируются (FOR UPDATE) до конца транзакции:
    два админа, одновременно понижающие друг друга, выполнятся по очереди, и второй
    увидит, что он последний.
    """
    await session.execute(select(Role.id).where(Role.is_superuser.is_(True)).with_for_update())
    return int(
        await session.scalar(
            select(func.count())
            .select_from(User)
            .join(Role, Role.code == User.role)
            .where(Role.is_superuser.is_(True), User.is_active.is_(True), User.id != exclude_user_id)
        )
        or 0
    )


async def _is_superuser_role(session: AsyncSession, code: str) -> bool:
    return bool(await session.scalar(select(Role.is_superuser).where(Role.code == code)))


@router.get("/admin/users", response_model=list[UserListRead])
async def list_users(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    rows = (
        await session.execute(select(User, Role.name).outerjoin(Role, Role.code == User.role).order_by(User.id))
    ).all()
    return [{**UserListRead.model_validate(u).model_dump(), "role_name": name or u.role} for u, name in rows]


@router.post("/admin/users", response_model=UserListRead)
async def create_user(
    data: UserCreate,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    role = await resolve_role(session, data.role)
    user = User(
        username=data.username.strip(),
        password=hash_password(data.password),
        full_name=data.full_name,
        role=role.code,
        is_active=data.is_active,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    _set_audit(request, f"Создан пользователь {user.username}, роль «{role.name}»")
    return {**UserListRead.model_validate(user).model_dump(), "role_name": role.name}


@router.patch("/admin/users/{user_id}", response_model=UserListRead)
async def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    update_data = data.model_dump(exclude_unset=True)
    changes: list[str] = []

    new_role: Role | None = None
    if update_data.get("role") is not None and update_data["role"] != user.role:
        new_role = await resolve_role(session, update_data["role"])
        update_data["role"] = new_role.code
    else:
        update_data.pop("role", None)

    deactivating = update_data.get("is_active") is False and user.is_active
    if update_data.get("is_active") is None:
        update_data.pop("is_active", None)

    # Защита от потери управления системой.
    if user.id == current_user.id:
        if new_role is not None:
            raise HTTPException(status_code=400, detail="Нельзя сменить роль самому себе")
        if deactivating:
            raise HTTPException(status_code=400, detail="Нельзя деактивировать самого себя")
    losing_superuser = user.is_active and await _is_superuser_role(session, user.role) and (
        deactivating or (new_role is not None and not new_role.is_superuser)
    )
    if losing_superuser and await _count_other_active_superusers(session, user.id) == 0:
        raise HTTPException(status_code=400, detail="Нельзя понизить или деактивировать последнего активного администратора")

    if update_data.get("username") is not None:
        update_data["username"] = update_data["username"].strip()
    else:
        update_data.pop("username", None)
    if update_data.get("password") is not None:
        update_data["password"] = hash_password(update_data["password"])
    else:
        update_data.pop("password", None)

    if "username" in update_data and update_data["username"] != user.username:
        changes.append(f"логин {user.username} → {update_data['username']}")
    if new_role is not None:
        changes.append(f"роль {user.role} → {new_role.code}")
    if "password" in update_data:
        changes.append("пароль изменён")
    if "is_active" in update_data and update_data["is_active"] != user.is_active:
        changes.append("активирован" if update_data["is_active"] else "деактивирован")

    for key, value in update_data.items():
        setattr(user, key, value)

    # Смена пароля или деактивация — немедленно отзываем все активные сессии пользователя.
    if ("password" in update_data) or deactivating:
        await session.execute(delete(UserSession).where(UserSession.user_id == user.id))

    await session.flush()
    await session.refresh(user)
    role_name = await session.scalar(select(Role.name).where(Role.code == user.role))
    payload = {**UserListRead.model_validate(user).model_dump(), "role_name": role_name or user.role}
    # Сначала фиксируем изменение, потом вытесняем кеш авторизации (см. AuthCache).
    await session.commit()
    auth_cache.evict_user(user.id)
    _set_audit(request, f"Пользователь {user.username}: " + ("; ".join(changes) or "без изменений"))
    return payload


@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.is_active and await _is_superuser_role(session, user.role):
        if await _count_other_active_superusers(session, user.id) == 0:
            raise HTTPException(status_code=400, detail="Нельзя удалить последнего активного администратора")

    _set_audit(request, f"Удалён пользователь {user.username}")
    await session.delete(user)
    await session.commit()
    auth_cache.evict_user(user_id)
    return None


# --- Роли -----------------------------------------------------------------------------


async def _users_count_by_role(session: AsyncSession) -> dict[str, int]:
    rows = (await session.execute(select(User.role, func.count()).group_by(User.role))).all()
    return {code: int(n) for code, n in rows}


def _role_payload(role: Role, users_count: int) -> dict:
    return {
        **{c: getattr(role, c) for c in ("id", "code", "name", "description", "is_system", "is_superuser",
                                         "revision", "created_at", "updated_at")},
        "permissions": normalize_permissions(role.permissions) if not role.is_superuser else {
            s["key"]: "full" for s in SECTIONS
        },
        "users_count": users_count,
    }


async def _name_taken(session: AsyncSession, name: str, exclude_id: int | None = None) -> bool:
    # Сравнение в Python (casefold): lower() в БД зависит от локали и может не понимать кириллицу.
    rows = (await session.execute(select(Role.id, Role.name))).all()
    target = name.strip().casefold()
    return any(rid != exclude_id and (rname or "").strip().casefold() == target for rid, rname in rows)


async def _ensure_unique_name(session: AsyncSession, name: str, exclude_id: int | None = None) -> None:
    if await _name_taken(session, name, exclude_id):
        raise HTTPException(status_code=409, detail="Роль с таким названием уже существует")


def _permissions_or_422(raw: object) -> dict[str, str]:
    try:
        return validate_permissions(raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _diff_permissions(old: dict[str, str], new: dict[str, str]) -> str:
    labels = {s["key"]: s["label"] for s in SECTIONS}
    parts = [
        f"{labels[k]}: {LEVEL_LABELS[old.get(k, 'none')].lower()} → {LEVEL_LABELS[new[k]].lower()}"
        for k in new
        if old.get(k, "none") != new[k]
    ]
    return "; ".join(parts)


async def _get_role_or_404(session: AsyncSession, role_id: int) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    return role


def _new_code() -> str:
    return f"r_{secrets.token_hex(4)}"


@router.get("/admin/roles/sections")
async def role_sections(_: User = Depends(require_admin)):
    """Справочник разделов и уровней — фронт не хардкодит список."""
    return {
        "sections": SECTIONS,
        "levels": [{"key": k, "label": LEVEL_LABELS[k], "hint": LEVEL_HINTS[k]} for k in LEVELS],
    }


@router.get("/admin/roles", response_model=list[RoleRead])
async def list_roles(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    counts = await _users_count_by_role(session)
    roles = (await session.execute(select(Role).order_by(Role.is_system.desc(), Role.id))).scalars().all()
    return [_role_payload(r, counts.get(r.code, 0)) for r in roles]


@router.post("/admin/roles", response_model=RoleRead)
async def create_role(
    data: RoleCreate,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Укажите название роли")
    await _ensure_unique_name(session, name)
    permissions = _permissions_or_422(data.permissions)
    role = Role(
        code=_new_code(),
        name=name,
        description=(data.description or "").strip() or None,
        is_system=False,
        is_superuser=False,  # вторую «админ-роль» создать нельзя
        permissions=permissions,
        revision=1,
    )
    session.add(role)
    await session.flush()
    await session.refresh(role)
    _set_audit(request, f"Создана роль «{role.name}» ({role.code}): {_diff_permissions({}, permissions) or 'без доступа'}")
    return _role_payload(role, 0)


@router.post("/admin/roles/{role_id}/copy", response_model=RoleRead)
async def copy_role(
    role_id: int,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    src = await _get_role_or_404(session, role_id)
    if src.is_superuser:
        raise HTTPException(status_code=400, detail="Системную роль администратора копировать нельзя")
    base = f"{src.name} (копия)"
    name, n = base, 2
    while await _name_taken(session, name):
        name, n = f"{base} {n}", n + 1
    role = Role(
        code=_new_code(),
        name=name[:128],
        description=src.description,
        permissions=normalize_permissions(src.permissions),
        revision=1,
    )
    session.add(role)
    await session.flush()
    await session.refresh(role)
    _set_audit(request, f"Роль «{src.name}» скопирована в «{role.name}» ({role.code})")
    return _role_payload(role, 0)


@router.patch("/admin/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    # FOR UPDATE: одновременные сохранения одной роли выполняются по очереди, ревизия растёт честно.
    role = await session.scalar(select(Role).where(Role.id == role_id).with_for_update())
    if role is None:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    if role.is_system:
        raise HTTPException(status_code=403, detail="Системная роль не редактируется")
    if data.revision is not None and data.revision != role.revision:
        raise HTTPException(status_code=409, detail="Роль уже изменена другим администратором — обновите страницу")

    changes: list[str] = []
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Укажите название роли")
        if name != role.name:
            await _ensure_unique_name(session, name, exclude_id=role.id)
            changes.append(f"название «{role.name}» → «{name}»")
            role.name = name
    if "description" in data.model_fields_set:
        role.description = (data.description or "").strip() or None
    if data.permissions is not None:
        new_perms = _permissions_or_422(data.permissions)
        old_perms = normalize_permissions(role.permissions)
        diff = _diff_permissions(old_perms, new_perms)
        if diff:
            changes.append(diff)
        role.permissions = dict(new_perms)  # новый объект — чтобы ORM точно увидел изменение JSON

    role.revision = (role.revision or 0) + 1
    await session.flush()
    await session.refresh(role)
    counts = await _users_count_by_role(session)
    payload = _role_payload(role, counts.get(role.code, 0))
    # Права применяются со следующего запроса (новая ревизия = новый ключ политики);
    # кеш авторизации вытесняем только после коммита.
    await session.commit()
    auth_cache.evict_role(role.code)
    _set_audit(request, f"Роль «{role.name}» ({role.code}): " + ("; ".join(changes) or "без изменений прав"))
    return payload


@router.delete("/admin/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    request: Request,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
):
    role = await _get_role_or_404(session, role_id)
    if role.is_system:
        raise HTTPException(status_code=403, detail="Системную роль удалить нельзя")
    usernames = (
        await session.execute(select(User.username).where(User.role == role.code).order_by(User.username).limit(11))
    ).scalars().all()
    if usernames:
        shown = ", ".join(usernames[:10]) + (" и др." if len(usernames) > 10 else "")
        raise HTTPException(
            status_code=409,
            detail=f"Роль назначена пользователям: {shown}. Сначала назначьте им другую роль.",
        )
    code = role.code
    _set_audit(request, f"Удалена роль «{role.name}» ({code})")
    await session.delete(role)
    await session.commit()
    auth_cache.evict_role(code)
    return None


# --- Журнал и состояние БД ------------------------------------------------------------


@router.get("/admin/audit-logs", response_model=list[AuditLogRead])
async def list_audit_logs(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db, scope="function"),
    limit: int = Query(200, ge=1, le=1000),
):
    result = await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return result.scalars().all()


@router.get("/admin/db-status")
async def db_status(_: User = Depends(require_admin)):
    """Пул приложения, соединения на сервере БД и кеш авторизации — без psql."""
    server: dict | None
    error: str | None = None
    try:
        server = await db_server_status()
    except Exception as e:  # noqa: BLE001
        server, error = None, f"{type(e).__name__}: {e}"
    return {
        "pool": pool_snapshot(),
        "server": server,
        "server_error": error,
        "auth_cache": {
            "enabled": auth_cache.enabled,
            "ttl_seconds": settings.auth_cache_ttl_seconds,
            "entries": len(auth_cache),
        },
        "policy_cache_entries": len(policy_cache),
    }
