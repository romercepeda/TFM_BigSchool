"""JWT session token creation and validation (Spec 00b §2, updated by Changeset C01).

A single session token is stored in an httpOnly cookie (pi_session).
JavaScript cannot read it — the browser sends it automatically on every request.
A separate, readable CSRF token (pi_csrf) is issued alongside and must be echoed
back in the X-CSRF-Token header on all state-changing requests.

Session token lifetime: 7 days (personal-use MVP default).
"""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError  # re-exported for callers

_ALGORITHM = "HS256"
SESSION_TOKEN_EXPIRE_DAYS = 7
SESSION_COOKIE_NAME = "pi_session"
CSRF_COOKIE_NAME = "pi_csrf"

__all__ = [
    "create_session_token",
    "decode_session_token",
    "SESSION_TOKEN_EXPIRE_DAYS",
    "SESSION_COOKIE_NAME",
    "CSRF_COOKIE_NAME",
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


def create_session_token(user_id: UUID, email: str) -> str:
    """Create a signed 7-day session token for the given user."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "session",
        "iat": now,
        "exp": now + timedelta(days=SESSION_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict:
    """Decode and validate a session token. Raises InvalidTokenError on failure."""
    payload = jwt.decode(token, _signing_key(), algorithms=[_ALGORITHM])
    if payload.get("type") != "session":
        raise InvalidTokenError("Token is not a session token.")
    return payload
