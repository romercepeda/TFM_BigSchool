"""Provider-agnostic market data service — Spec D09 §2 (data service layer).

This is the only module the rest of the application imports from D09.
All provider-specific code lives in the providers/ sub-package.

Public entry point:
    from app.services.market_data.service import get_market_data_service
"""

import logging
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.db.models.asset import Asset
from app.db.models.holding import Holding
from app.db.models.market_data import AssetPriceHistory, FxRateHistory
from app.services.market_data.providers.base import FxDataProvider, MarketDataProvider
from app.services.market_data.types import AssetSearchResult, FxPoint, PricePoint, ProviderError

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 400  # MA200 needs 200 trading days ≈ 285 calendar days; 400 gives safe margin

# US exchanges where no market prefix/suffix is needed.
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "OTC", "CBOE", "NMFQS"}


def _provider_symbol(ticker: str, market: str | None, provider: str = "finnhub") -> str:
    """Build the exchange-qualified symbol for the active market data provider.

    Twelve Data — non-US format: TICKER:MARKET (e.g. TEF:BME).

    Finnhub has no documented MARKET:TICKER or TICKER:MARKET convention for
    equities — its own /search endpoint returns non-US symbols already fully
    qualified with a dot suffix (e.g. TEF.MC), which the ':'/'.' passthrough
    below already handles. A bare ticker + separate market code (e.g. from a
    legacy asset row) cannot be reliably turned into that suffix, so it is
    passed through unqualified rather than guessing a wrong symbol.

    If the ticker already contains ':' or '.' it is assumed to be fully-qualified
    and is returned as-is regardless of provider.
    """
    if ':' in ticker or '.' in ticker:
        return ticker
    if market and market.upper() not in _US_EXCHANGES and provider == "twelve_data":
        return f"{ticker}:{market}"
    return ticker


class MarketDataService:
    def __init__(
        self,
        market_provider: MarketDataProvider,
        fx_provider: FxDataProvider,
        market_provider_name: str,
    ) -> None:
        self._market = market_provider
        self._fx = fx_provider
        self._provider_name = market_provider_name

    # ── Asset search — always live, never cached (D09 §8) ─────────────────────

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        return await self._market.search_assets(query)

    # ── Current price — on-demand fetch ───────────────────────────────────────

    async def get_current_price(self, ticker: str, market: str | None = None) -> PricePoint:
        return await self._market.get_current_price(_provider_symbol(ticker, market, self._provider_name))

    # ── FX pair support check ──────────────────────────────────────────────────

    async def is_fx_pair_supported(self, quote: str, base: str) -> bool:
        return await self._fx.is_pair_supported(quote, base)

    # ── Historical FX rate with DB cache (D09 §7.1) ───────────────────────────

    async def get_historical_fx_rate(
        self,
        db: AsyncSession,
        quote: str,
        base: str,
        on_date: date,
    ) -> Decimal | None:
        """Return the FX rate for a specific date. Checks DB first; fetches and persists if missing.

        Returns None if the provider call fails — caller decides how to handle the gap.
        Same-currency pairs always return Decimal("1") without a network call.
        """
        if quote.upper() == base.upper():
            return Decimal("1")

        row = await db.scalar(
            select(FxRateHistory).where(
                FxRateHistory.quote_currency == quote.upper(),
                FxRateHistory.base_currency == base.upper(),
                FxRateHistory.as_of_date == on_date,
            )
        )
        if row is not None:
            return row.rate

        try:
            point = await self._fx.get_historical_rate(quote, base, on_date)
        except ProviderError as exc:
            logger.warning("FX historical fetch failed %s/%s %s: %s", quote, base, on_date, exc)
            return None

        await self._persist_fx(db, point)
        return point.rate

    # ── Current FX rate — fetch and persist (D09 §7.2) ────────────────────────

    async def get_current_fx_rate(self, db: AsyncSession, quote: str, base: str) -> Decimal:
        """Return the current FX rate and persist it to FxRateHistory.

        Per D09 §7.2: subsequent same-day calls for the same pair read from the DB.
        Same-currency pairs return Decimal("1") without a network call.
        Raises ProviderError if the provider call fails.
        """
        if quote.upper() == base.upper():
            return Decimal("1")

        point = await self._fx.get_current_rate(quote, base)
        await self._persist_fx(db, point)
        return point.rate

    async def _persist_fx(self, db: AsyncSession, point: FxPoint) -> None:
        stmt = (
            pg_insert(FxRateHistory)
            .values(
                quote_currency=point.quote_currency,
                base_currency=point.base_currency,
                as_of_date=point.as_of_date,
                rate=point.rate,
                provider="frankfurter",
                fetched_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing()
        )
        await db.execute(stmt)

    # ── Daily price update job (D09 §6) ───────────────────────────────────────

    async def run_daily_update(self, db: AsyncSession) -> dict:
        """Fetch prices for every active-holding asset and trigger the D06 alert engine.

        Stops early on rate-limit errors (D09 §6.3). Failure on one asset does not
        abort the rest. Returns a summary dict for the caller / API response.
        """
        from app.db.models.portfolio import Portfolio
        from app.services.price_level_service import apply_crossings

        today = date.today()
        start_date = today - timedelta(days=_LOOKBACK_DAYS)

        # Distinct assets with at least one active holding across all users.
        assets_result = await db.execute(
            select(Asset)
            .join(Holding, Holding.asset_id == Asset.id)
            .join(Portfolio, Portfolio.id == Holding.portfolio_id)
            .where(Portfolio.status == "active")
            .distinct()
        )
        assets = list(assets_result.scalars().all())
        logger.info("Daily update: %d assets to process.", len(assets))

        from app.services.indicator_service import run_daily_indicators

        processed = 0
        failed = 0
        alerts = 0
        indicator_snapshots = 0

        for asset in assets:
            try:
                points = await self._market.get_historical_series(
                    _provider_symbol(asset.ticker, asset.market, self._provider_name), start_date, today
                )
            except ProviderError as exc:
                if exc.error_kind == "rate_limited":
                    logger.warning(
                        "Rate limit reached at asset %s — stopping job early.", asset.ticker
                    )
                    break
                logger.error("Price fetch failed for %s: %s", asset.ticker, exc)
                failed += 1
                continue

            # Persist new dates (ON CONFLICT DO NOTHING keeps history immutable).
            now = datetime.now(UTC)
            for point in points:
                ins = pg_insert(AssetPriceHistory).values(
                    asset_id=asset.id,
                    as_of_date=point.as_of_date,
                    close_price=point.price,
                    volume=point.volume,
                    provider=self._provider_name,
                    fetched_at=now,
                )
                # Backfill volume on rows that were inserted before we stored it.
                # close_price is kept immutable (not in set_).
                stmt = ins.on_conflict_do_update(
                    constraint="uq_asset_price_date",
                    set_={"volume": ins.excluded.volume},
                    where=AssetPriceHistory.volume.is_(None),
                )
                await db.execute(stmt)

            # D05: compute scheduled_daily technical indicators from the fetched series.
            sorted_points = sorted(points, key=lambda p: p.as_of_date)
            prices_sorted = [p.price for p in sorted_points]
            volumes_sorted = [p.volume for p in sorted_points]
            try:
                written = await run_daily_indicators(db, asset, prices_sorted, today, volumes=volumes_sorted)
                indicator_snapshots += written
            except Exception as exc:
                logger.error("Indicator job failed for %s: %s", asset.ticker, exc)

            # Get the two most recent stored closes for the alert engine (D06).
            recent_result = await db.execute(
                select(AssetPriceHistory)
                .where(AssetPriceHistory.asset_id == asset.id)
                .order_by(AssetPriceHistory.as_of_date.desc())
                .limit(2)
            )
            recent = list(recent_result.scalars().all())

            if len(recent) >= 2:
                current_close = recent[0].close_price
                previous_close = recent[1].close_price
                close_date = recent[0].as_of_date

                holdings_result = await db.execute(
                    select(Holding).where(Holding.asset_id == asset.id)
                )
                for holding in holdings_result.scalars().all():
                    crossed = await apply_crossings(
                        db,
                        holding.id,
                        previous_close=previous_close,
                        current_close=current_close,
                        close_date=close_date,
                    )
                    alerts += len(crossed)

            processed += 1

        await db.commit()
        logger.info(
            "Daily update complete: processed=%d failed=%d alerts=%d indicators=%d",
            processed, failed, alerts, indicator_snapshots,
        )
        return {
            "assets_processed": processed,
            "assets_failed": failed,
            "alerts_triggered": alerts,
            "indicator_snapshots": indicator_snapshots,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────


_service: MarketDataService | None = None


def get_market_data_service() -> MarketDataService:
    """Return the cached service instance. Built on first call from config + env vars."""
    global _service
    if _service is None:
        _service = _build_service()
    return _service


def _build_service() -> MarketDataService:
    from app.services.market_data.providers.finnhub import FinnhubProvider
    from app.services.market_data.providers.frankfurter import FrankfurterProvider
    from app.services.market_data.providers.twelve_data import TwelveDataProvider

    cfg = get_config()

    fx_provider = FrankfurterProvider(base_url=cfg.fx_data.frankfurter.base_url)

    # Pre-cascade legacy path (USE_CASCADE=false) — only ever looks at the
    # first entry of the cascade list and only knows twelve_data/finnhub.
    # Retired once Changeset C04 Step 7 flips USE_CASCADE=true; a "eodhd"
    # or unrecognized first entry here falls through to finnhub, same as
    # before this changeset (single active provider, no cascade wiring yet).
    if cfg.market_data.providers[0] == "twelve_data":
        api_key = os.environ.get("MARKET_DATA_TWELVE_DATA_API_KEY", "")
        if not api_key:
            logger.warning("MARKET_DATA_TWELVE_DATA_API_KEY not set — provider calls will fail.")
        market_provider: MarketDataProvider = TwelveDataProvider(
            base_url=cfg.market_data.twelve_data.base_url,
            api_key=api_key,
        )
        provider_name = "twelve_data"
    else:
        api_key = os.environ.get("MARKET_DATA_FINNHUB_API_KEY", "")
        if not api_key:
            logger.warning("MARKET_DATA_FINNHUB_API_KEY not set — provider calls will fail.")
        market_provider = FinnhubProvider(
            base_url=cfg.market_data.finnhub.base_url,
            api_key=api_key,
        )
        provider_name = "finnhub"

    return MarketDataService(
        market_provider=market_provider,
        fx_provider=fx_provider,
        market_provider_name=provider_name,
    )
