"""Startup permission-coverage validator — Spec D11 §8.3.

Runs once at application startup, after all routers are registered and the
roles catalog has been seeded. Two checks, both fail-fast (SystemExit(1)):

  1. Every route outside the small pre-authentication/infrastructure allowlist
     has exactly one require_permission dependency (D11 §8.2's "single
     permission per endpoint" rule, enforced structurally here).
  2. Every require_permission code referenced anywhere exists in the currently
     loaded permissions catalog.

This is what makes the permission model auditable: a route with zero or a
stale/renamed permission code fails startup instead of silently allowing (zero
checks) or always-403ing (unknown code) at runtime.
"""

import logging

from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.role import Permission
from app.roles.dependencies import RequirePermission

logger = logging.getLogger(__name__)

# Routes intentionally NOT gated by a permission:
#   - GET /health: infrastructure liveness probe (Docker, load balancers) — no
#     auth context exists yet, and D11's catalog has no "health" domain.
#   - POST /auth/register, /auth/login, /auth/guest: pre-authentication entry
#     points. require_permission depends on get_current_user, which by
#     definition cannot succeed before a session exists.
#   - POST /auth/logout: must succeed even with an expired/invalid/missing
#     session cookie, so it cannot depend on get_current_user either.
_UNGUARDED_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/guest"),
    ("POST", "/auth/logout"),
}


def _extract_permission_codes(route: APIRoute) -> list[str]:
    return [
        dep.call.code
        for dep in route.dependant.dependencies
        if isinstance(dep.call, RequirePermission)
    ]


async def validate_permission_coverage(app: FastAPI, db: AsyncSession) -> None:
    """Fail startup if any non-allowlisted route lacks exactly one valid permission."""
    result = await db.execute(select(Permission.code).where(Permission.active.is_(True)))
    valid_codes = {row[0] for row in result.all()}

    errors: list[str] = []
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            if (method, route.path) in _UNGUARDED_ROUTES:
                continue
            checked += 1
            codes = _extract_permission_codes(route)
            if len(codes) == 0:
                errors.append(f"{method} {route.path} — no require_permission dependency")
            elif len(codes) > 1:
                errors.append(
                    f"{method} {route.path} — {len(codes)} require_permission "
                    f"dependencies (expected exactly one): {codes}"
                )
            elif codes[0] not in valid_codes:
                errors.append(
                    f"{method} {route.path} — unknown permission code {codes[0]!r}"
                )

    if errors:
        logger.critical(
            "Permission coverage check failed for %d of %d route(s):\n  %s",
            len(errors), checked, "\n  ".join(errors),
        )
        raise SystemExit(1)

    logger.info("Permission coverage check passed for all %d route(s).", checked)
