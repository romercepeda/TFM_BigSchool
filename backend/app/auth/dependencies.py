"""FastAPI dependencies for authentication (Changeset C01 — cookie-based session).

get_current_user reads the pi_session httpOnly cookie, validates the JWT,
and fetches the user from the database.

    from app.auth.dependencies import get_current_user
    from app.db.models.user import User

    @router.get("/protected")
    async def protected(current_user: User = Depends(get_current_user)):
        return {"email": current_user.email}

Raises HTTP 401 if the cookie is absent, expired, or invalid.
"""

from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import SESSION_COOKIE_NAME, InvalidTokenError, decode_session_token
from app.db.models.user import User
from app.db.session import get_db

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired session. Please log in again.",
)


async def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the session cookie and return the authenticated User entity."""
    if session_token is None:
        raise _UNAUTHORIZED

    try:
        payload = decode_session_token(session_token)
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise _UNAUTHORIZED

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _UNAUTHORIZED

    return user
