"""FastAPI dependencies for authentication.

get_current_user is the reusable dependency that protects any endpoint
that requires a logged-in user. Use it like this:

    from app.auth.dependencies import get_current_user
    from app.db.models.user import User

    @router.get("/protected")
    async def protected(current_user: User = Depends(get_current_user)):
        return {"email": current_user.email}

The dependency reads the Bearer token from the Authorization header,
validates the JWT signature and expiry, and fetches the user from the DB.
It raises HTTP 401 if anything fails — and the error message is intentionally
vague to avoid leaking information about why validation failed.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import InvalidTokenError, decode_access_token
from app.db.models.user import User
from app.db.session import get_db

_bearer = HTTPBearer()

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the Bearer JWT and return the authenticated User entity."""
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise _UNAUTHORIZED

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _UNAUTHORIZED

    return user
