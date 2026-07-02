"""Administration API endpoints — Spec D11 §7.2, §7.3.

Endpoints:
    GET    /admin/users                        — paginated user list
    GET    /admin/users/{user_id}               — user detail
    POST   /admin/users/{user_id}/roles         — grant a role
    DELETE /admin/users/{user_id}/roles/{code}  — revoke a role
    POST   /admin/users/{user_id}/reset-password — reset another user's password
    GET    /admin/roles                         — read-only role + permission listing

Every endpoint requires exactly one permission per D11 §8.2, matching the
catalog's user.*/role.* domain (D11 §5.1).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_schemas import (
    AdminRoleOut,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserSummary,
    AssignRoleRequest,
    ResetPasswordResponse,
)
from app.auth.dependencies import get_current_user
from app.config import get_config
from app.db.models.portfolio import Portfolio
from app.db.models.role import Permission, Role, RolePermission
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.roles.service import LastAdminError, assign_role, get_role_codes, revoke_role
from app.services.i18n_service import translate, translate_role_description, translate_role_name
from app.services.user_service import admin_reset_password, get_user_by_id

router = APIRouter(prefix="/admin", tags=["admin"])

_USER_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")


def _last_admin_conflict(lang: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "last_admin",
            "message": translate("error.last_admin", lang),
        },
    )


async def _to_summary(db: AsyncSession, user: User) -> AdminUserSummary:
    roles = await get_role_codes(db, user.id)
    return AdminUserSummary(
        id=user.id,
        email=user.email,
        auth_provider=user.auth_provider,
        display_name=user.display_name,
        roles=roles,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


async def _role_permission_codes(db: AsyncSession, role_id: UUID) -> list[str]:
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id, Permission.active.is_(True))
    )
    return sorted(row[0] for row in result.all())


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    dependencies=[Depends(require_permission("user.list"))],
)
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """Paginated list of every user in the system (D11 §7.2)."""
    total = await db.scalar(select(func.count()).select_from(User))
    result = await db.execute(
        select(User).order_by(User.created_at.asc()).limit(limit).offset(offset)
    )
    users = list(result.scalars().all())
    items = [await _to_summary(db, u) for u in users]
    return AdminUserListResponse(items=items, total=total or 0)


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    dependencies=[Depends(require_permission("user.view_any"))],
)
async def get_user_detail(user_id: UUID, db: AsyncSession = Depends(get_db)) -> AdminUserDetail:
    """Full detail for one user, including their active-portfolio count (D11 §7.2)."""
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _USER_NOT_FOUND
    return await _build_user_detail(db, user)


async def _build_user_detail(db: AsyncSession, user: User) -> AdminUserDetail:
    roles = await get_role_codes(db, user.id)
    portfolios_count = await db.scalar(
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.user_id == user.id, Portfolio.status == "active")
    )
    return AdminUserDetail(
        id=user.id,
        email=user.email,
        auth_provider=user.auth_provider,
        display_name=user.display_name,
        roles=roles,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        portfolios_count=portfolios_count or 0,
    )


@router.post(
    "/users/{user_id}/roles",
    response_model=AdminUserDetail,
    dependencies=[Depends(require_permission("role.assign"))],
)
async def grant_role(
    user_id: UUID,
    body: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetail:
    """Grant a role to a user (D11 §7.3). Idempotent."""
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _USER_NOT_FOUND

    try:
        await assign_role(
            db, user_id=user.id, role_code=body.role_code, assigned_by_user_id=current_user.id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return await _build_user_detail(db, user)


@router.delete(
    "/users/{user_id}/roles/{role_code}",
    response_model=AdminUserDetail,
    dependencies=[Depends(require_permission("role.revoke"))],
)
async def revoke_role_endpoint(
    user_id: UUID,
    role_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminUserDetail:
    """Revoke a role from a user (D11 §7.3).

    Returns 409 if this is the user's last Administrator assignment and no
    other active administrator exists (D11 §6.3) — an administrator CAN revoke
    their own admin role if at least one other user still holds it.
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _USER_NOT_FOUND

    try:
        await revoke_role(db, user_id=user.id, role_code=role_code)
    except LastAdminError as exc:
        raise _last_admin_conflict(current_user.preferred_language) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return await _build_user_detail(db, user)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    dependencies=[Depends(require_permission("user.change_any_password"))],
)
async def reset_password(
    user_id: UUID, db: AsyncSession = Depends(get_db)
) -> ResetPasswordResponse:
    """Reset another user's password to a new random value (D11 §7.2, §7.4).

    The new password is returned once in this response and never stored or
    logged in plaintext. must_change_password is set true on the target.
    """
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise _USER_NOT_FOUND
    if user.auth_provider != "password":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset is not available for this account type.",
        )

    cfg = get_config()
    new_password = await admin_reset_password(
        db, user, password_length=cfg.security.default_admin_password_length
    )
    return ResetPasswordResponse(new_password=new_password)


@router.get(
    "/roles",
    response_model=list[AdminRoleOut],
    dependencies=[Depends(require_permission("role.list"))],
)
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AdminRoleOut]:
    """Read-only listing of every active role and the permissions it holds (D11 §7.2)."""
    cfg = get_config()
    lang = current_user.preferred_language
    default_lang = cfg.i18n.default_language

    result = await db.execute(select(Role).where(Role.active.is_(True)).order_by(Role.code.asc()))
    roles = list(result.scalars().all())
    out = []
    for role in roles:
        permissions = await _role_permission_codes(db, role.id)
        out.append(AdminRoleOut(
            code=role.code,
            name=translate_role_name(role.name_key, lang, default_lang),
            description=translate_role_description(role.description_key, lang, default_lang),
            is_default=role.is_default,
            is_admin_role=role.is_admin_role,
            permissions=permissions,
        ))
    return out
