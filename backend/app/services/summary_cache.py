"""In-memory TTL cache for PortfolioSummary — Changeset C08 §5.

Process-local (no Redis): each backend worker keeps its own cache, an
accepted trade-off for the personal-use MVP. The key includes the current
UTC date, so a day rollover busts every entry for free without a separate
sweep — only the TTL and explicit invalidate() need to be handled here.

cachetools is not a project dependency (confirmed before writing this), so
this is the ~30-line hand-written version the changeset allows as the
fallback.
"""

import time
from datetime import UTC, date, datetime
from uuid import UUID

from app.api.portfolio_schemas import PortfolioSummary
from app.config import get_config

_CacheKey = tuple[UUID, UUID, date]  # (portfolio_id, user_id, current_date_utc)

_store: dict[_CacheKey, tuple[PortfolioSummary, float]] = {}  # key -> (summary, inserted_at)


def _key(portfolio_id: UUID, user_id: UUID) -> _CacheKey:
    return (portfolio_id, user_id, datetime.now(UTC).date())


def get_cached(portfolio_id: UUID, user_id: UUID) -> PortfolioSummary | None:
    """Return the cached summary if present and within TTL, else None.

    Caching is disabled when portfolio.summary.cache_ttl_seconds is 0 (Spec
    00f §9 — useful for debugging), in which case this always returns None.
    """
    ttl = get_config().portfolio.summary.cache_ttl_seconds
    if ttl <= 0:
        return None

    key = _key(portfolio_id, user_id)
    entry = _store.get(key)
    if entry is None:
        return None

    summary, inserted_at = entry
    if time.monotonic() - inserted_at > ttl:
        del _store[key]
        return None
    return summary


def store(portfolio_id: UUID, user_id: UUID, summary: PortfolioSummary) -> None:
    if get_config().portfolio.summary.cache_ttl_seconds <= 0:
        return
    _store[_key(portfolio_id, user_id)] = (summary, time.monotonic())


def invalidate(portfolio_id: UUID) -> None:
    """Drop every cached entry for this portfolio, regardless of user_id or date.

    Called by the lot/sale/holding write paths after a successful commit
    (Changeset C08 §5) — a portfolio's summary must never serve stale totals
    after its holdings change.
    """
    for key in [k for k in _store if k[0] == portfolio_id]:
        del _store[key]
