"""Roles & permissions catalog seed loader — Spec D11 §3.

Reads roles_catalog.yaml at startup and upserts it into the permissions, roles,
and role_permissions tables. The file is the single source of truth: any DB row
whose code is no longer present in the file is marked inactive (not deleted).

Mirrors the D05 indicator-catalog loader (app.services.indicator_service.seed_indicators).
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.role import Permission, Role, RolePermission

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).parent.parent.parent / "roles_catalog.yaml"


# ── Catalog shape validation (Pydantic) ───────────────────────────────────────


class PermissionEntry(BaseModel):
    code: str
    name_key: str
    description_key: str


class RoleEntry(BaseModel):
    code: str
    name_key: str
    description_key: str
    is_default: bool
    is_admin_role: bool
    permissions: list[str]


class RolesCatalog(BaseModel):
    permissions: list[PermissionEntry]
    roles: list[RoleEntry]

    @model_validator(mode="after")
    def _check_shape(self) -> "RolesCatalog":
        perm_codes = [p.code for p in self.permissions]
        if len(perm_codes) != len(set(perm_codes)):
            raise ValueError("duplicate permission code(s) in catalog")

        role_codes = [r.code for r in self.roles]
        if len(role_codes) != len(set(role_codes)):
            raise ValueError("duplicate role code(s) in catalog")

        default_roles = [r.code for r in self.roles if r.is_default]
        if len(default_roles) != 1:
            raise ValueError(
                f"exactly one role must have is_default: true, found {len(default_roles)} "
                f"({default_roles})"
            )

        admin_roles = [r.code for r in self.roles if r.is_admin_role]
        if len(admin_roles) != 1:
            raise ValueError(
                f"exactly one role must have is_admin_role: true, found {len(admin_roles)} "
                f"({admin_roles})"
            )

        perm_code_set = set(perm_codes)
        for role in self.roles:
            unknown = set(role.permissions) - perm_code_set
            if unknown:
                raise ValueError(
                    f"role {role.code!r} references unknown permission code(s): {sorted(unknown)}"
                )

        return self


# ── Seed loading (D11 §3) ─────────────────────────────────────────────────────


async def seed_roles_catalog(db: AsyncSession) -> None:
    """Upsert roles_catalog.yaml into the DB. Fails fast on missing/malformed file.

    Called at application startup, after seed_indicators (Spec D05) and before
    the app starts accepting requests. Per spec §3:
    - new permission/role code -> insert
    - existing code -> update mutable fields
    - code removed from catalog -> mark active=False (rows retained)
    - role_permissions refreshed to match the file exactly
    """
    if not _CATALOG_PATH.exists():
        logger.critical("roles_catalog.yaml not found at %s — cannot start.", _CATALOG_PATH)
        raise SystemExit(1)

    with open(_CATALOG_PATH) as f:
        raw = yaml.safe_load(f) or {}

    try:
        catalog = RolesCatalog.model_validate(raw)
    except ValidationError as exc:
        logger.critical("roles_catalog.yaml is malformed — cannot start.\n%s", exc)
        raise SystemExit(1) from exc

    now = datetime.now(UTC)

    permission_ids = await _upsert_permissions(db, catalog.permissions, now)
    role_ids = await _upsert_roles(db, catalog.roles, now)
    await _refresh_role_permissions(db, catalog.roles, permission_ids, role_ids)

    await db.commit()
    logger.info(
        "Roles catalog seeded: %d permissions, %d roles.",
        len(catalog.permissions), len(catalog.roles),
    )


async def _upsert_permissions(
    db: AsyncSession, entries: list[PermissionEntry], now: datetime
) -> dict[str, UUID]:
    catalog_codes = {e.code for e in entries}
    existing_rows = await db.execute(select(Permission))
    by_code: dict[str, Permission] = {perm.code: perm for perm in existing_rows.scalars().all()}

    for entry in entries:
        existing = by_code.get(entry.code)
        if existing is None:
            perm = Permission(
                code=entry.code,
                name_key=entry.name_key,
                description_key=entry.description_key,
                active=True,
            )
            db.add(perm)
            by_code[entry.code] = perm
        else:
            existing.name_key = entry.name_key
            existing.description_key = entry.description_key
            existing.active = True
            existing.updated_at = now

    for code, perm in by_code.items():
        if code not in catalog_codes and perm.active:
            perm.active = False
            perm.updated_at = now

    await db.flush()
    return {code: perm.id for code, perm in by_code.items()}


async def _upsert_roles(
    db: AsyncSession, entries: list[RoleEntry], now: datetime
) -> dict[str, UUID]:
    catalog_codes = {e.code for e in entries}
    existing_rows = await db.execute(select(Role))
    by_code: dict[str, Role] = {role.code: role for role in existing_rows.scalars().all()}

    for entry in entries:
        existing = by_code.get(entry.code)
        if existing is None:
            role = Role(
                code=entry.code,
                name_key=entry.name_key,
                description_key=entry.description_key,
                is_default=entry.is_default,
                is_admin_role=entry.is_admin_role,
                active=True,
            )
            db.add(role)
            by_code[entry.code] = role
        else:
            existing.name_key = entry.name_key
            existing.description_key = entry.description_key
            existing.is_default = entry.is_default
            existing.is_admin_role = entry.is_admin_role
            existing.active = True
            existing.updated_at = now

    for code, role in by_code.items():
        if code not in catalog_codes and role.active:
            role.active = False
            role.updated_at = now

    await db.flush()
    return {code: role.id for code, role in by_code.items()}


async def _refresh_role_permissions(
    db: AsyncSession,
    entries: list[RoleEntry],
    permission_ids: dict[str, UUID],
    role_ids: dict[str, UUID],
) -> None:
    """Make role_permissions match the catalog exactly for every role in the file."""
    for entry in entries:
        role_id = role_ids[entry.code]
        desired = {permission_ids[code] for code in entry.permissions}

        result = await db.execute(
            select(RolePermission).where(RolePermission.role_id == role_id)
        )
        existing_rows = list(result.scalars().all())
        existing = {row.permission_id for row in existing_rows}

        for row in existing_rows:
            if row.permission_id not in desired:
                await db.delete(row)

        for permission_id in desired - existing:
            db.add(RolePermission(role_id=role_id, permission_id=permission_id))
