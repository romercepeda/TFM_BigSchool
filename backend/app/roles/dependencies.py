"""Permission enforcement — Spec D11 §8. Also carries the must_change_password
guard (D11 §6.4) since both checks need the same current_user dependency.

Every FastAPI endpoint declares its required permission via:

    @router.post("/portfolios", dependencies=[Depends(require_permission("portfolio.create"))])

The startup validator (app.roles.validation, called from app.main) scans every
registered route and verifies each has exactly one require_permission dependency
referencing a code that exists in the loaded catalog (D11 §8.3) — except the small,
explicit allowlist of pre-authentication / infrastructure routes in app.roles.validation.

While a user's must_change_password flag is true, every gated endpoint except
POST /auth/change-password itself returns HTTP 428 instead of running its normal
permission check (D11 §6.4) — this is the server-side half of the "cannot navigate
elsewhere" rule; the frontend router enforces the same rule for UX (D11 §7.4).
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.roles.service import get_effective_permissions
from app.services.i18n_service import translate

# The one endpoint (POST /auth/change-password) exempt from the must_change_password
# guard below — otherwise a user who must change their password could never call the
# only endpoint that lets them do so (D11 §6.4).
_CHANGE_PASSWORD_PERMISSION = "user.change_own_password"


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
        if (
            current_user.must_change_password
            and self.code != _CHANGE_PASSWORD_PERMISSION
        ):
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "code": "must_change_password",
                    "message": translate(
                        "error.must_change_password", current_user.preferred_language
                    ),
                },
            )

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
