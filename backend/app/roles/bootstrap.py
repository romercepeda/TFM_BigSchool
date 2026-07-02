"""Bootstrap the initial administrator account — Spec D11 §6.1, §6.3.

Runs at every startup, after the roles catalog (Change 1) has been seeded and
after the schema/backfill changes (Changes 2-3) have applied, so the account
this module creates actually has the Administrator role's permissions
attached from the moment it exists.

Two responsibilities, called in sequence from app.main's lifespan:
  1. ensure_admin_exists() — creates the configured admin account the first
     time no user anywhere holds the administrator role.
  2. verify_always_one_admin() — independently fails startup if the
     always-one-admin invariant does not hold (D11 §6.3), e.g. because an
     administrator revoked their own role via the UI leaving zero admins, or
     a database restore wiped the assignment.
"""

import logging
import secrets
import string
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.db.models.role import Role, UserRole
from app.services.user_service import create_user, get_user_by_email

logger = logging.getLogger(__name__)

# No ambiguous characters: excludes 0/O and 1/l/I (D11 §6.1 step 2).
_PASSWORD_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)

_BANNER_RULE = "=" * 69
_BANNER_SUBRULE = "-" * 69


def _generate_password(length: int) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


async def _get_admin_role(db: AsyncSession) -> Role:
    role = await db.scalar(
        select(Role).where(Role.is_admin_role.is_(True), Role.active.is_(True))
    )
    if role is None:
        raise RuntimeError(
            "No active role with is_admin_role: true found in the roles catalog. "
            "Check roles_catalog.yaml and that the seed loader has run at startup."
        )
    return role


async def _any_active_admin_exists(db: AsyncSession, admin_role_id: UUID) -> bool:
    result = await db.scalar(
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.role_id == admin_role_id, Role.active.is_(True))
        .limit(1)
    )
    return result is not None


async def ensure_admin_exists(db: AsyncSession) -> None:
    """Create the configured administrator account if no admin exists yet (D11 §6.1)."""
    admin_role = await _get_admin_role(db)

    if await _any_active_admin_exists(db, admin_role.id):
        return

    cfg = get_config()
    email = cfg.security.default_admin_email

    existing = await get_user_by_email(db, email)
    if existing is not None:
        raise SystemExit(
            f"No administrator exists, and security.default_admin_email ({email!r}) "
            "already belongs to an existing account. Refusing to modify it silently. "
            "Change security.default_admin_email in config.yaml to an unused address, "
            "or manually assign the administrator role to this existing account and "
            "restart. SQL to do the latter:\n\n"
            "  INSERT INTO user_roles (user_id, role_id, assigned_at, assigned_by_user_id)\n"
            f"  VALUES ('{existing.id}', '{admin_role.id}', now(), NULL);"
        )

    password = _generate_password(cfg.security.default_admin_password_length)
    user = await create_user(
        db,
        email=email,
        auth_provider="password",
        password=password,
        must_change_password=True,
        assign_default_role=False,
    )
    db.add(UserRole(user_id=user.id, role_id=admin_role.id, assigned_by_user_id=None))
    await db.commit()

    logger.info(
        "\n%s\n"
        "INITIAL ADMINISTRATOR ACCOUNT CREATED\n"
        "%s\n"
        "Email:    %s\n"
        "Password: %s\n"
        "%s\n"
        "This password is shown ONLY at first startup. It will not be shown\n"
        "again. The user MUST change it on first login (see must_change_password).\n"
        "%s",
        _BANNER_RULE, _BANNER_SUBRULE, email, password, _BANNER_SUBRULE, _BANNER_RULE,
    )


async def verify_always_one_admin(db: AsyncSession) -> None:
    """Fail startup if no active user holds the administrator role (D11 §6.3)."""
    admin_role = await _get_admin_role(db)
    if await _any_active_admin_exists(db, admin_role.id):
        return

    logger.critical(
        "No user holds the administrator role (%s). The system has no admin "
        "authority and cannot recover from the UI. Manual recovery: connect to "
        "the database and run (substituting the target user's id):\n\n"
        "  INSERT INTO user_roles (user_id, role_id, assigned_at, assigned_by_user_id)\n"
        "  VALUES ('<user-id>', '%s', now(), NULL);",
        admin_role.code, admin_role.id,
    )
    raise SystemExit(1)
