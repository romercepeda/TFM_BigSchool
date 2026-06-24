"""CSRF protection — double-submit cookie pattern (Changeset C01 §1).

At login:
  1. generate_csrf_token() creates a random token.
  2. The caller sets it as a non-httpOnly cookie (pi_csrf) — JavaScript can read it.
  3. The frontend reads the cookie and sends its value in X-CSRF-Token on
     every state-changing request (POST/PUT/PATCH/DELETE).

The middleware (registered in main.py) validates the header against the cookie
on every unsafe method. GET/HEAD/OPTIONS are exempt.
Unauthenticated requests (no pi_csrf cookie) are skipped here — they will be
rejected by get_current_user instead.
"""

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


async def csrf_middleware(request: Request, call_next):
    if request.method not in _SAFE_METHODS:
        cookie_value = request.cookies.get("pi_csrf")
        if cookie_value is not None:  # only enforce when a session cookie exists
            header_value = request.headers.get(CSRF_HEADER)
            if not header_value or not secrets.compare_digest(cookie_value, header_value):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid."},
                )
    return await call_next(request)
