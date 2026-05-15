from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ADMIN_ROLE, hash_password, make_token, normalize_role, require_admin, verify_password, write_audit_log
from app.database import get_db
from app.models import AuditLog, User
from app.schemas.common import AuditLogRead, AuthToken, UserCreate, UserLogin, UserRead, UserUpdate

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=AuthToken)
async def login(data: UserLogin, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(data.password, user.password):
        await write_audit_log(session, user, "POST", "/auth/login", 401, f"Неуспешный вход: {data.username}")
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    user.session_token = make_token()
    await session.flush()
    await session.refresh(user)
    await write_audit_log(session, user, "POST", "/auth/login", 200, "Вход в систему")
    return {"token": user.session_token, "user": user}


@router.get("/auth/me", response_model=UserRead)
async def me(request: Request):
    return request.state.user


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, session: AsyncSession = Depends(get_db)):
    user = await session.get(User, request.state.user.id)
    if user:
        user.session_token = None
        await session.flush()
    return None


@router.get("/admin/users", response_model=list[UserRead])
async def list_users(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("/admin/users", response_model=UserRead)
async def create_user(
    data: UserCreate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    role = normalize_role(data.role)
    user = User(
        username=data.username.strip(),
        password=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        is_active=data.is_active,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@router.patch("/admin/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    data: UserUpdate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    update_data = data.model_dump(exclude_unset=True)
    if "role" in update_data and update_data["role"] is not None:
        update_data["role"] = normalize_role(update_data["role"])
    if "username" in update_data and update_data["username"] is not None:
        update_data["username"] = update_data["username"].strip()
    if "password" in update_data and update_data["password"] is not None:
        update_data["password"] = hash_password(update_data["password"])

    for key, value in update_data.items():
        setattr(user, key, value)

    await session.flush()
    await session.refresh(user)
    return user


@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.role == ADMIN_ROLE:
        admin_count = await session.scalar(select(func.count()).select_from(User).where(User.role == ADMIN_ROLE))
        if (admin_count or 0) <= 1:
            raise HTTPException(status_code=400, detail="Нельзя удалить последнего администратора")

    await session.delete(user)
    return None


@router.get("/admin/audit-logs", response_model=list[AuditLogRead])
async def list_audit_logs(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(200, ge=1, le=1000),
):
    result = await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return result.scalars().all()
