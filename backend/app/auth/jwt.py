"""JWT token creation and validation (Spec 00b §2).

Access tokens: short-lived (15 min), sent in the Authorization header.
Refresh tokens: long-lived (30 days), stored in an httpOnly cookie
                so JavaScript cannot read them.

Both tokens carry a `type` claim ("access" or "refresh") to prevent
one type from being accepted where the other is expected.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError  # re-exported for callers

_ALGORITHM = "HS256"
_ACCESS_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30
REFRESH_COOKIE_NAME = "refresh_token"

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "REFRESH_COOKIE_NAME",
    "InvalidTokenError",
]


def _signing_key() -> str:
    key = os.environ.get("JWT_SIGNING_KEY", "")
    if not key:
        raise RuntimeError(
            "JWT_SIGNING_KEY environment variable is not set. "
            "Set it in .env (local dev) or in the cloud secret manager (production)."
        )
    return key


def create_access_token(user_id: UUID, email: str) -> str:
    """Create a signed access token for the given user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=_ACCESS_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Create a signed refresh token for the given user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token. Raises InvalidTokenError on failure."""
    payload = jwt.decode(token, _signing_key(), algorithms=[_ALGORITHM])
    if payload.get("type") != "access":
        raise InvalidTokenError("Token is not an access token.")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token. Raises InvalidTokenError on failure."""
    payload = jwt.decode(token, _signing_key(), algorithms=[_ALGORITHM])
    if payload.get("type") != "refresh":
        raise InvalidTokenError("Token is not a refresh token.")
    return payload
