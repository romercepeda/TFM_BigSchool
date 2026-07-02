"""Role assignment and permission-resolution business logic — Spec D11 §4.4, §6.2, §7.3, §8.

Change 3 of Changeset C02 uses the default-role lookup, the single-user
assignment helper, and the startup backfill. Change 5 and Change 6 use
get_effective_permissions and get_role_codes (the FastAPI-facing wiring for
Change 5 lives in app.roles.dependencies, which calls into this module).
Change 8 uses assign_role/revoke_role (admin role management, with the
last-admin protection) and generate_password (also used by bootstrap.py's
initial-admin creation, D11 §6.1).
"""

import logging
import secrets
import string
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.role import Permission, Role, RolePermission, UserRole
from app.db.models.user import User

logger = logging.getLogger(__name__)

# Looked up once per process and reused — the default role does not change
# without a restart (the seed loader only runs at startup), matching the
# caching note in Changeset C02 §3.
_default_role_id_cache: UUID | None = None

# No ambiguous characters: excludes 0/O and 1/l/I (D11 §6.1 step 2).
_PASSWORD_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)


class LastAdminError(Exception):
    """Raised by revoke_role when it would leave zero active administrators (D11 §6.3, §7.3)."""


def generate_password(length: int) -> str:
    """Cryptographically random password: URL-safe alphabet, no ambiguous characters."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


async def get_default_role_id(db: AsyncSession) -> UUID:
    """Return the id of the role marked `is_default: true` in the catalog.

    Raises RuntimeError if no active default role exists in the DB — this is a
    catalog misconfiguration (missing seed run, or a bad roles_catalog.yaml)
    and must fail loudly at the point of use rather than silently skip role
    assignment (Changeset C02 §3 acceptance criteria).
    """
    global _default_role_id_cache
    if _default_role_id_cache is not None:
        return _default_role_id_cache

    role = await db.scalar(
        select(Role).where(Role.is_default.is_(True), Role.active.is_(True))
    )
    if role is None:
        raise RuntimeError(
            "No active role with is_default: true found in the roles catalog. "
            "Check roles_catalog.yaml and that the seed loader has run at startup."
        )
    _default_role_id_cache = role.id
    return role.id


async def grant_default_role(db: AsyncSession, user_id: UUID) -> None:
    """Assign the default role to a newly registered user (D11 §6.2).

    assigned_by_user_id is left null: this is an automatic assignment, not an
    administrator action. Caller is responsible for flush/commit.
    """
    role_id = await get_default_role_id(db)
    db.add(UserRole(user_id=user_id, role_id=role_id, assigned_by_user_id=None))
    await db.flush()


async def backfill_default_roles(db: AsyncSession) -> int:
    """Assign the default role to every existing User with no UserRole row yet.

    One-off data migration per Changeset C02 §3, run at startup (after the
    roles catalog has been seeded) rather than inside the Alembic migration,
    because the default role does not exist in the DB until the seed loader
    runs — which happens after migrations in this project's startup sequence.
    Idempotent: safe to run on every startup, a no-op once every user has a role.
    """
    role_id = await get_default_role_id(db)
    result = await db.execute(
        select(User.id)
        .outerjoin(UserRole, UserRole.user_id == User.id)
        .where(UserRole.user_id.is_(None))
    )
    user_ids = [row[0] for row in result.all()]

    for user_id in user_ids:
        db.add(UserRole(user_id=user_id, role_id=role_id, assigned_by_user_id=None))

    if user_ids:
        await db.commit()
        logger.info("Backfilled default role for %d existing user(s).", len(user_ids))

    return len(user_ids)


async def get_effective_permissions(db: AsyncSession, user_id: UUID) -> set[str]:
    """Return the flat union of permission codes across all of a user's active roles.

    Only active permissions/roles count — a role or permission removed from the
    catalog (D11 §3) stops granting access even if a stale UserRole row remains.
    """
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            UserRole.user_id == user_id,
            Permission.active.is_(True),
            Role.active.is_(True),
        )
        .distinct()
    )
    return {row[0] for row in result.all()}


async def get_role_codes(db: AsyncSession, user_id: UUID) -> list[str]:
    """Return the codes of every active role the user holds (D11 §8.4 login payload)."""
    result = await db.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.active.is_(True))
    )
    return [row[0] for row in result.all()]


async def _get_role_by_code(db: AsyncSession, role_code: str) -> Role:
    role = await db.scalar(select(Role).where(Role.code == role_code, Role.active.is_(True)))
    if role is None:
        raise ValueError(f"Unknown or inactive role code: {role_code!r}")
    return role


async def assign_role(
    db: AsyncSession, *, user_id: UUID, role_code: str, assigned_by_user_id: UUID
) -> None:
    """Grant a role to a user (D11 §7.3). Idempotent — a no-op if already held."""
    role = await _get_role_by_code(db, role_code)
    existing = await db.scalar(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )
    if existing is not None:
        return
    db.add(UserRole(user_id=user_id, role_id=role.id, assigned_by_user_id=assigned_by_user_id))
    await db.commit()


async def revoke_role(db: AsyncSession, *, user_id: UUID, role_code: str) -> None:
    """Revoke a role from a user (D11 §7.3).

    Raises LastAdminError, without changing anything, if this would leave zero
    active administrators (D11 §6.3) — the caller maps that to HTTP 409.
    Idempotent — a no-op if the user doesn't hold the role.
    """
    role = await _get_role_by_code(db, role_code)

    if role.is_admin_role:
        other_admins = await db.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.id == role.id,
                Role.active.is_(True),
                UserRole.user_id != user_id,
            )
        )
        if not other_admins:
            raise LastAdminError()

    existing = await db.scalar(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )
    if existing is None:
        return
    await db.delete(existing)
    await db.commit()
