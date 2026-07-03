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

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppConfig, get_config
from app.db.models.asset import Asset
from app.db.models.holding import Holding
from app.db.models.market_data import AssetPriceHistory, FxRateHistory
from app.services.market_data.cascade import FxDataCascade, MarketDataCascade
from app.services.market_data.providers.base import FxDataProvider, MarketDataProvider
from app.services.market_data.types import AssetSearchResult, FxPoint, PricePoint, ProviderError

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 400  # MA200 needs 200 trading days ≈ 285 calendar days; 400 gives safe margin

# Cascade-path-only bootstrap window (Spec D12 §5.3). Deliberately under
# EODHD's 365-day provider_max_lookback_days cap — at 400 (_LOOKBACK_DAYS
# above) EODHD would be skipped on *every* bootstrap request, never actually
# getting a chance to rescue a brand-new asset that Twelve Data/Finnhub
# can't serve (e.g. a European ticker outside their free tiers). 350 still
# comfortably covers MA200's ~285-day need.
_CASCADE_BOOTSTRAP_LOOKBACK_DAYS = 350


def _cascade_enabled() -> bool:
    """Spec D12 / Changeset C04 §10 feature flag.

    Defaults to enabled as of Step 7 ("this is the moment behavior changes
    for end users"). Set USE_CASCADE=false to fall back to the pre-cascade
    single-provider path if needed.
    """
    return os.environ.get("USE_CASCADE", "true").strip().lower() == "true"

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


_NO_PROVIDER_MESSAGE = "No market data provider is configured (market_data.providers is empty)."


class _NoProviderConfigured(MarketDataProvider):
    """Placeholder used when an admin has emptied market_data.providers (D12 §7.2).

    Fails clearly on every call rather than crashing the service with an
    IndexError when there is no "primary" provider to build.
    """

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        raise ProviderError(
            error_kind="api_error", retryable=False, upstream_message=_NO_PROVIDER_MESSAGE
        )

    async def get_current_price(self, ticker: str) -> PricePoint:
        raise ProviderError(
            error_kind="api_error", retryable=False, upstream_message=_NO_PROVIDER_MESSAGE
        )

    async def get_historical_series(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PricePoint]:
        raise ProviderError(
            error_kind="api_error", retryable=False, upstream_message=_NO_PROVIDER_MESSAGE
        )


class MarketDataService:
    def __init__(
        self,
        market_provider: MarketDataProvider,
        fx_provider: FxDataProvider,
        market_provider_name: str,
        *,
        market_cascade: MarketDataCascade | None = None,
        fx_cascade: FxDataCascade | None = None,
    ) -> None:
        self._market = market_provider
        self._fx = fx_provider
        self._provider_name = market_provider_name
        # Both None until Changeset C04 Step 7 flips USE_CASCADE=true. Only
        # the daily update (market) and FX rate lookups (fx) consult the
        # cascade (D12 §5.1/§5.2) — get_current_price and search_assets stay
        # on the single first-in-list provider, per D12's scope (§5.5 for
        # search; get_current_price is an on-demand lookup D12 doesn't cover).
        self._market_cascade = market_cascade
        self._fx_cascade = fx_cascade

    # ── Asset search — always live, never cached (D09 §8) ─────────────────────

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        return await self._market.search_assets(query)

    # ── Current price — on-demand fetch ───────────────────────────────────────

    async def get_current_price(self, ticker: str, market: str | None = None) -> PricePoint:
        return await self._market.get_current_price(_provider_symbol(ticker, market, self._provider_name))

    # ── FX pair support check ──────────────────────────────────────────────────

    async def is_fx_pair_supported(self, quote: str, base: str) -> bool:
        if self._fx_cascade is not None:
            return await self._fx_cascade.is_pair_supported(quote, base)
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
            if self._fx_cascade is not None:
                point, _provider = await self._fx_cascade.get_historical_rate(quote, base, on_date)
            else:
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

        if self._fx_cascade is not None:
            point, _provider = await self._fx_cascade.get_current_rate(quote, base)
        else:
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

        Delegates to the cascade-enabled path (Spec D12 §5, Changeset C04) when
        this service was built with a market_cascade — see _build_service().
        """
        if self._market_cascade is not None:
            return await self._run_daily_update_cascade(db)

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

    # ── Cascade-enabled daily update (Spec D12 §5, Changeset C04) ─────────────
    #
    # Deliberately duplicates most of run_daily_update()'s per-asset persist/
    # indicator/alert logic rather than sharing it: the two paths coexist only
    # for the migration window behind USE_CASCADE, and Changeset C04 Step 7
    # deletes run_daily_update()'s single-provider body entirely once the flag
    # is always on, at which point this becomes the only implementation.
    # Unifying them now would mean touching the live path before Step 7.

    async def _run_daily_update_cascade(self, db: AsyncSession) -> dict:
        """Cascade-enabled daily update. Same persistence/indicator/alert
        behavior as run_daily_update(), but resolves prices via
        MarketDataCascade and persists a CascadeFailureReport (D12 §6)
        instead of just counting failures.

        Splits assets into a bootstrap window (full _LOOKBACK_DAYS, for
        assets with no stored history yet) and an incremental window (just
        enough to cover the gap since the stalest asset's last stored date,
        for assets that already have history). Without this split every
        request would need the full ~400-day window, and EODHD's 365-day
        cap (provider_max_lookback_days) would make the cascade skip it on
        every single run — defeating its purpose as an incremental fallback
        (D12 §5.3).
        """
        from app.db.models.portfolio import Portfolio
        from app.services.indicator_service import run_daily_indicators
        from app.services.market_data.cascade import CascadeAssetRequest, merge_cascade_results
        from app.services.market_data.cascade_reports import (
            cleanup_old_cascade_reports,
            persist_cascade_result,
        )
        from app.services.price_level_service import apply_crossings

        assert self._market_cascade is not None  # only called when set

        cfg = get_config()
        today = date.today()

        assets_result = await db.execute(
            select(Asset)
            .join(Holding, Holding.asset_id == Asset.id)
            .join(Portfolio, Portfolio.id == Holding.portfolio_id)
            .where(Portfolio.status == "active")
            .distinct()
        )
        assets = list(assets_result.scalars().all())
        assets_by_id = {a.id: a for a in assets}
        logger.info("Cascade daily update: %d assets to process.", len(assets))

        last_stored_result = await db.execute(
            select(AssetPriceHistory.asset_id, func.max(AssetPriceHistory.as_of_date))
            .where(AssetPriceHistory.asset_id.in_([a.id for a in assets]))
            .group_by(AssetPriceHistory.asset_id)
        )
        last_stored_date_by_asset = dict(last_stored_result.all())

        bootstrap_assets = [a for a in assets if a.id not in last_stored_date_by_asset]
        incremental_assets = [a for a in assets if a.id in last_stored_date_by_asset]

        cascade_results = []
        if bootstrap_assets:
            requests = [
                CascadeAssetRequest(asset_id=a.id, ticker=a.ticker, market=a.market)
                for a in bootstrap_assets
            ]
            start_date = today - timedelta(days=_CASCADE_BOOTSTRAP_LOOKBACK_DAYS)
            cascade_results.append(
                await self._market_cascade.execute(requests, start_date, today)
            )
        if incremental_assets:
            requests = [
                CascadeAssetRequest(asset_id=a.id, ticker=a.ticker, market=a.market)
                for a in incremental_assets
            ]
            # Sized by the stalest asset in this batch, so nobody's gap is
            # missed even if the job hasn't run in a while.
            oldest_last_date = min(
                last_stored_date_by_asset[a.id] for a in incremental_assets
            )
            cascade_results.append(
                await self._market_cascade.execute(requests, oldest_last_date, today)
            )

        cascade_result = merge_cascade_results(cascade_results)

        alerts = 0
        indicator_snapshots = 0

        for asset_id, success in cascade_result.resolved.items():
            asset = assets_by_id[asset_id]

            now = datetime.now(UTC)
            for point in success.points:
                ins = pg_insert(AssetPriceHistory).values(
                    asset_id=asset.id,
                    as_of_date=point.as_of_date,
                    close_price=point.price,
                    volume=point.volume,
                    provider=success.provider,
                    fetched_at=now,
                )
                stmt = ins.on_conflict_do_update(
                    constraint="uq_asset_price_date",
                    set_={"volume": ins.excluded.volume},
                    where=AssetPriceHistory.volume.is_(None),
                )
                await db.execute(stmt)

            sorted_points = sorted(success.points, key=lambda p: p.as_of_date)
            prices_sorted = [p.price for p in sorted_points]
            volumes_sorted = [p.volume for p in sorted_points]
            try:
                written = await run_daily_indicators(
                    db, asset, prices_sorted, today, volumes=volumes_sorted
                )
                indicator_snapshots += written
            except Exception as exc:
                logger.error("Indicator job failed for %s: %s", asset.ticker, exc)

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

        report = await persist_cascade_result(db, cascade_result)
        deleted = await cleanup_old_cascade_reports(
            db, retention_days=cfg.market_data.failure_report_retention_days
        )
        if deleted:
            logger.info("Cascade report cleanup: removed %d report(s) past retention.", deleted)

        await db.commit()
        logger.info(
            "Cascade daily update complete: processed=%d failed=%d alerts=%d indicators=%d",
            len(cascade_result.resolved), len(cascade_result.failures), alerts, indicator_snapshots,
        )
        return {
            "assets_processed": len(cascade_result.resolved),
            "assets_failed": len(cascade_result.failures),
            "alerts_triggered": alerts,
            "indicator_snapshots": indicator_snapshots,
            "cascade_report_id": str(report.id),
        }


# ── Module-level singleton ─────────────────────────────────────────────────────


_service: MarketDataService | None = None


def get_market_data_service() -> MarketDataService:
    """Return the cached service instance. Built on first call from config + env vars."""
    global _service
    if _service is None:
        _service = _build_service()
    return _service


def reset_market_data_service() -> None:
    """Drop the cached instance so the next call rebuilds it.

    Called after a Settings-driven change to the provider lists (Changeset
    C04 §5) so the new order is used immediately (D12 §7.2), not just after
    a restart.
    """
    global _service
    _service = None


def _build_market_provider_adapter(name: str, cfg: AppConfig) -> MarketDataProvider:
    """Instantiate one market data adapter by its config-key name.

    Shared by the single "primary" provider (get_current_price/search_assets,
    D12 §5.5 — never cascaded) and, when USE_CASCADE=true, every entry of the
    full cascade list.
    """
    from app.services.market_data.providers.eodhd import EODHDProvider
    from app.services.market_data.providers.finnhub import FinnhubProvider
    from app.services.market_data.providers.twelve_data import TwelveDataProvider

    if name == "eodhd":
        api_key = os.environ.get("MARKET_DATA_EODHD_API_KEY", "")
        if not api_key:
            logger.warning("MARKET_DATA_EODHD_API_KEY not set — provider calls will fail.")
        return EODHDProvider(
            base_url=cfg.market_data.eodhd.base_url,
            api_key=api_key,
            daily_call_budget=cfg.market_data.eodhd.daily_call_budget,
        )
    if name == "finnhub":
        api_key = os.environ.get("MARKET_DATA_FINNHUB_API_KEY", "")
        if not api_key:
            logger.warning("MARKET_DATA_FINNHUB_API_KEY not set — provider calls will fail.")
        return FinnhubProvider(base_url=cfg.market_data.finnhub.base_url, api_key=api_key)

    # "twelve_data" and any unrecognized name (schema already restricts the
    # Literal to these three, so this is unreachable in practice).
    api_key = os.environ.get("MARKET_DATA_TWELVE_DATA_API_KEY", "")
    if not api_key:
        logger.warning("MARKET_DATA_TWELVE_DATA_API_KEY not set — provider calls will fail.")
    return TwelveDataProvider(base_url=cfg.market_data.twelve_data.base_url, api_key=api_key)


def _build_service() -> MarketDataService:
    from app.services import settings_overlay
    from app.services.market_data.providers.frankfurter import FrankfurterProvider

    cfg = get_config()

    fx_provider = FrankfurterProvider(base_url=cfg.fx_data.frankfurter.base_url)

    # Settings-editable lists (Changeset C04 §5) — a DB override, if an
    # admin has saved one, wins over config.yaml's value.
    market_data_providers = settings_overlay.get_market_data_providers(cfg.market_data.providers)
    fx_data_providers = settings_overlay.get_fx_data_providers(cfg.fx_data.providers)

    # The single "primary" provider — used by get_current_price/search_assets
    # regardless of USE_CASCADE (D12 §5.5: search never cascades; on-demand
    # current-price lookups aren't in D12's cascade scope either).
    if market_data_providers:
        primary_name = market_data_providers[0]
        market_provider: MarketDataProvider = _build_market_provider_adapter(primary_name, cfg)
    else:
        primary_name = ""
        market_provider = _NoProviderConfigured()

    market_cascade: MarketDataCascade | None = None
    fx_cascade: FxDataCascade | None = None
    if _cascade_enabled():
        market_cascade = MarketDataCascade(
            [
                (name, _build_market_provider_adapter(name, cfg))
                for name in market_data_providers
            ]
        )
        # v1 has a single FX provider (D12 §5.2); wrapped in the cascade
        # anyway so a second one is a config change, not a code change.
        fx_cascade = FxDataCascade([(name, fx_provider) for name in fx_data_providers])

    return MarketDataService(
        market_provider=market_provider,
        fx_provider=fx_provider,
        market_provider_name=primary_name,
        market_cascade=market_cascade,
        fx_cascade=fx_cascade,
    )
