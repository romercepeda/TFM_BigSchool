"""CSRF protection — double-submit cookie pattern (Changeset C01 §1).

At login:
  1. generate_csrf_token() creates a random token.
  2. The caller sets it as a non-httpOnly cookie (pi_csrf) and also returns it
     in the login response body (see api/auth.py) — the frontend cannot rely
     on document.cookie because frontend and backend are on different
     hostnames in production, so it keeps the value in memory instead.
  3. The frontend sends that value in X-CSRF-Token on every state-changing
     request (POST/PUT/PATCH/DELETE).

The middleware (registered in main.py) validates the header against the cookie
on every unsafe method. GET/HEAD/OPTIONS are exempt.

Login-issuing endpoints (register/login/guest) are also exempt: they don't
act on an existing session, so there is nothing for CSRF to protect, and
requiring the header there is a chicken-and-egg problem — the frontend only
learns the CSRF value from a successful login response. Without this
exemption, a browser that already holds a leftover pi_csrf cookie (e.g. from
an earlier session) would be locked out of logging back in at all.
"""

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_AUTH_ISSUING_PATHS = {"/auth/register", "/auth/login", "/auth/guest"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


async def csrf_middleware(request: Request, call_next):
    if request.method not in _SAFE_METHODS and request.url.path not in _AUTH_ISSUING_PATHS:
        cookie_value = request.cookies.get("pi_csrf")
        if cookie_value is not None:  # only enforce when a session cookie exists
            header_value = request.headers.get(CSRF_HEADER)
            if not header_value or not secrets.compare_digest(cookie_value, header_value):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid."},
                )
    return await call_next(request)
