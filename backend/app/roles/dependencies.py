"""Permission enforcement — Spec D11 §8.

Every FastAPI endpoint declares its required permission via:

    @router.post("/portfolios", dependencies=[Depends(require_permission("portfolio.create"))])

The startup validator (app.roles.validation, called from app.main) scans every
registered route and verifies each has exactly one require_permission dependency
referencing a code that exists in the loaded catalog (D11 §8.3) — except the small,
explicit allowlist of pre-authentication / infrastructure routes in app.roles.validation.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models.role import Permission, Role, RolePermission, UserRole
from app.db.models.user import User
from app.db.session import get_db
from app.services.i18n_service import translate


async def get_effective_permissions(db: AsyncSession, user_id: UUID) -> set[str]:
    """Return the flat union of permission codes across all of a user's active roles.

    Only active permissions/roles count — a role or permission removed from the
    catalog (D11 §3) stops granting access even if a stale UserRole row remains.
    """
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == user_id,
            Permission.active.is_(True),
            Role.active.is_(True),
        )
        .distinct()
    )
    return {row[0] for row in result.all()}


class RequirePermission:
    """Callable FastAPI dependency. A class instance (not a closure) so the
    startup validator can introspect `.code` on every route via `isinstance`.
    """

    def __init__(self, code: str) -> None:
        self.code = code

    async def __call__(
        self,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        # Exactly one require_permission per endpoint (D11 §8.2) means this runs
        # at most once per request — no extra request-scoped cache is needed
        # beyond FastAPI's own dependency cache, which already dedupes the
        # get_current_user lookup above across the whole dependency tree.
        permissions = await get_effective_permissions(db, current_user.id)
        if self.code not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    # Never reveal which permission was required (D11 §7.5).
                    "message": translate(
                        "error.permission_denied", current_user.preferred_language
                    ),
                },
            )


def require_permission(code: str) -> RequirePermission:
    return RequirePermission(code)
