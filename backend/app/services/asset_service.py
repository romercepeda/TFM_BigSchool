"""Asset business logic — get-or-create by ticker, search.

Assets are shared reference data: one row per ticker across all users.
Created on-demand when a user first adds that asset to any portfolio (Spec D03 §3.1).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset


async def get_asset_by_ticker(db: AsyncSession, ticker: str) -> Asset | None:
    result = await db.execute(select(Asset).where(Asset.ticker == ticker.upper()))
    return result.scalar_one_or_none()


async def get_or_create_asset(
    db: AsyncSession,
    *,
    ticker: str,
    name: str,
    asset_type: str,
    quote_currency: str,
    market: str | None = None,
) -> tuple[Asset, bool]:
    """Return (asset, created). If the ticker already exists, return the existing record.

    The existing record's name/type/market are NOT updated — the first creator wins.
    This is intentional: shared reference data must not silently change under other users.
    """
    ticker = ticker.upper()
    existing = await get_asset_by_ticker(db, ticker)
    if existing is not None:
        return existing, False

    asset = Asset(
        ticker=ticker,
        name=name,
        asset_type=asset_type,
        quote_currency=quote_currency.upper(),
        market=market,
    )
    db.add(asset)
    await db.flush()
    return asset, True


async def search_assets(db: AsyncSession, query: str, limit: int = 20) -> list[Asset]:
    """Search assets by ticker prefix or name substring."""
    q = query.strip().upper()
    result = await db.execute(
        select(Asset)
        .where(
            Asset.ticker.startswith(q) | Asset.name.ilike(f"%{query.strip()}%")
        )
        .order_by(Asset.ticker.asc())
        .limit(limit)
    )
    return list(result.scalars().all())
