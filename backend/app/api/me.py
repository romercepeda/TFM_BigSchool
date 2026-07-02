"""Current-user permission refresh — Spec D11 §8.4.

POST /me/refresh-permissions — returns the same user shape as the login
response (id, email, display_name, preferred_language, must_change_password,
roles, permissions) for the currently authenticated user, recomputed from the
DB. Lets the frontend pick up a role change without forcing a re-login —
e.g. an administrator who just granted themselves a role in the same session.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import LoginUserOut
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.roles.service import get_effective_permissions, get_role_codes

router = APIRouter(prefix="/me", tags=["me"])


@router.post(
    "/refresh-permissions",
    response_model=LoginUserOut,
    dependencies=[Depends(require_permission("settings.view_own"))],
)
async def refresh_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoginUserOut:
    """Recompute and return the caller's roles/permissions/must_change_password."""
    roles = await get_role_codes(db, current_user.id)
    permissions = await get_effective_permissions(db, current_user.id)
    return LoginUserOut(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        preferred_language=current_user.preferred_language,
        must_change_password=current_user.must_change_password,
        roles=roles,
        permissions=sorted(permissions),
    )
