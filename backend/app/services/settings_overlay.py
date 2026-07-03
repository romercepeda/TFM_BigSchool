"""In-memory cache for the `system_settings` DB overlay — Spec D12 §7, Changeset C04 §5.

Only two config keys are overridable at runtime: `market_data.providers` and
`fx_data.providers`. Everything else in config.yaml stays file-only and
requires a restart (Spec 00f §5) — this is a narrow, documented exception.

Why an in-memory cache instead of querying the DB on every read: the market
data service builds its provider adapters in a synchronous, DB-independent
singleton (`market_data/service.py::_build_service`). Threading a DB session
through that call path would mean either making it async everywhere it's
called or opening a throwaway session just for this — a bigger change than
this narrow exception warrants. Instead, the cache is populated once at
startup and kept in sync by whichever request updates a value.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

MARKET_DATA_PROVIDERS_KEY = "market_data.providers"
FX_DATA_PROVIDERS_KEY = "fx_data.providers"

_overrides: dict[str, list[str]] = {}


async def load_overrides(db: AsyncSession) -> None:
    """Populate the in-memory cache from the DB. Call once at startup."""
    result = await db.execute(select(SystemSetting))
    _overrides.clear()
    for row in result.scalars().all():
        _overrides[row.key] = row.value
    if _overrides:
        logger.info("Loaded %d system_settings override(s): %s", len(_overrides), list(_overrides))


def get_market_data_providers(default: list[str]) -> list[str]:
    return _overrides.get(MARKET_DATA_PROVIDERS_KEY, default)


def get_fx_data_providers(default: list[str]) -> list[str]:
    return _overrides.get(FX_DATA_PROVIDERS_KEY, default)


async def set_override(
    db: AsyncSession, key: str, value: list[str], *, updated_by_user_id: UUID
) -> None:
    stmt = (
        pg_insert(SystemSetting)
        .values(key=key, value=value, updated_by_user_id=updated_by_user_id)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": value, "updated_by_user_id": updated_by_user_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    _overrides[key] = value


async def reset_override(
    db: AsyncSession, key: str, default_value: list[str], *, updated_by_user_id: UUID
) -> None:
    """Reset to the shipped default (D12 §3) — an explicit override, not a delete.

    A future config.yaml edit to a different value should not silently
    resurrect once an admin has reset via this endpoint.
    """
    await set_override(db, key, default_value, updated_by_user_id=updated_by_user_id)
