"""D09 — Market & FX Data Integration API endpoints.

GET  /market-data/assets/search?q=       — live provider typeahead (D09 §8)
GET  /market-data/assets/{ticker}/price  — last known price, cache-only (Changeset C19)
POST /market-data/assets/{ticker}/price/refresh — live re-fetch, on demand (Changeset C19)
GET  /market-data/fx/rate                — current FX rate, persisted to FxRateHistory
GET  /market-data/fx/supported           — check if a currency pair is supported
POST /market-data/daily-update           — trigger the daily price + alert job (D09 §6)
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d09_schemas import (
    AssetSearchResultResponse,
    DailyUpdateResponse,
    FxPairSupportedResponse,
    FxRateResponse,
    PricePointResponse,
)
from app.auth.dependencies import get_current_user
from app.db.models.asset import Asset
from app.db.models.market_data import AssetPriceHistory
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services.market_data.service import get_market_data_service
from app.services.market_data.types import ProviderError

router = APIRouter(prefix="/market-data", tags=["market-data"])


async def _last_known_price(db: AsyncSession, ticker: str) -> AssetPriceHistory | None:
    """Changeset C14 — most recent stored price for a ticker, if any.

    Used to keep showing a usable value when the live provider call fails,
    instead of the hard "no disponible" error the endpoint raised before.
    """
    asset = await db.scalar(select(Asset).where(Asset.ticker == ticker))
    if asset is None:
        return None
    return await db.scalar(
        select(AssetPriceHistory)
        .where(AssetPriceHistory.asset_id == asset.id)
        .order_by(AssetPriceHistory.as_of_date.desc())
        .limit(1)
    )


def _unavailable(exc: ProviderError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": "Datos no disponibles — el proveedor no está accesible en este momento.",
            "error_kind": exc.error_kind,
            "retryable": exc.retryable,
            "upstream": exc.upstream_message,
        },
    )


@router.get(
    "/assets/search",
    response_model=list[AssetSearchResultResponse],
    dependencies=[Depends(require_permission("holding.add_asset"))],
)
async def search_assets(
    q: str = Query(min_length=1, description="Ticker or company name prefix."),
    current_user: User = Depends(get_current_user),
) -> list[AssetSearchResultResponse]:
    """Live typeahead via the configured market data provider (D09 §8).

    Results are NOT cached — every call hits the provider.
    Use GET /assets/search to search the local DB of already-added assets.
    """
    svc = get_market_data_service()
    try:
        results = await svc.search_assets(q)
    except ProviderError as exc:
        raise _unavailable(exc)
    return [
        AssetSearchResultResponse(
            ticker=r.ticker,
            name=r.name,
            asset_type=r.asset_type,
            quote_currency=r.quote_currency,
            market=r.market,
        )
        for r in results
    ]


@router.get(
    "/assets/{ticker}/price",
    response_model=PricePointResponse,
    dependencies=[Depends(require_permission("holding.view"))],
)
async def get_asset_price(
    ticker: str,
    exchange: str | None = Query(default=None, description="Unused — kept for URL compatibility."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PricePointResponse:
    """Return the last known price for a ticker — cache-only, no live provider call.

    Changeset C19: this used to call the live provider on every request, which
    meant every asset-detail page view (and every set-levels page view) spent
    one call against the market-data provider's daily quota. It now only reads
    AssetPriceHistory (written by the daily job, or by a prior manual refresh —
    see POST .../price/refresh below). Raises 503 only when no price has ever
    been stored for the asset (brand-new asset, daily job hasn't run for it yet
    and nobody has refreshed it manually).
    """
    ticker_upper = ticker.upper()
    fallback = await _last_known_price(db, ticker_upper)
    if fallback is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": "Datos no disponibles — aún no se ha obtenido un precio para este activo.",
                "error_kind": "no_data",
                "retryable": True,
            },
        )
    return PricePointResponse(
        ticker=ticker_upper,
        as_of_date=fallback.as_of_date,
        price=fallback.close_price,
        fetched_at=fallback.fetched_at,
    )


@router.post(
    "/assets/{ticker}/price/refresh",
    response_model=PricePointResponse,
    dependencies=[Depends(require_permission("holding.view"))],
)
async def refresh_asset_price(
    ticker: str,
    exchange: str | None = Query(default=None, description="Market/exchange code, e.g. BME, LSE."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PricePointResponse:
    """On-demand live re-fetch of a single asset's current price (Changeset C19).

    This is the only path left that calls the live provider outside the daily
    job — triggered explicitly by the user via the refresh icon on the asset
    detail screen's "Current Price" card, never automatically. Per D09 §5.3,
    the result is NOT written to AssetPriceHistory (that table is
    append-only/immutable per trading day, owned by the daily job); this is a
    transient value shown to the user with its own fetch timestamp, same as
    the live branch that used to run on every page load.

    Falls back to the last known stored price if the live call fails —
    identical fallback semantics to Changeset C14, just moved behind an
    explicit user action instead of running unconditionally.
    """
    svc = get_market_data_service()
    ticker_upper = ticker.upper()
    try:
        point = await svc.get_current_price(ticker_upper, exchange.upper() if exchange else None)
    except ProviderError as exc:
        fallback = await _last_known_price(db, ticker_upper)
        if fallback is None:
            raise _unavailable(exc)
        return PricePointResponse(
            ticker=ticker_upper,
            as_of_date=fallback.as_of_date,
            price=fallback.close_price,
            fetched_at=fallback.fetched_at,
        )
    return PricePointResponse(
        ticker=ticker_upper,
        as_of_date=point.as_of_date,
        price=point.price,
        fetched_at=datetime.now(UTC),
    )


@router.get(
    "/fx/rate",
    response_model=FxRateResponse,
    dependencies=[Depends(require_permission("holding.view"))],
)
async def get_fx_rate(
    quote_currency: str = Query(description="Asset currency — e.g. USD."),
    base_currency: str = Query(description="Portfolio currency — e.g. EUR."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FxRateResponse:
    """Return the current FX rate and persist it to FxRateHistory (D09 §7.2).

    Rate convention (D04 §3.1): 1 unit of quote_currency → rate units of base_currency.
    Subsequent calls within the same trading day return the cached DB value.
    """
    svc = get_market_data_service()
    try:
        rate = await svc.get_current_fx_rate(db, quote_currency.upper(), base_currency.upper())
    except ProviderError as exc:
        raise _unavailable(exc)
    await db.commit()
    return FxRateResponse(
        quote_currency=quote_currency.upper(),
        base_currency=base_currency.upper(),
        as_of_date=date.today(),
        rate=rate,
        provider="frankfurter",
    )


@router.get(
    "/fx/supported",
    response_model=FxPairSupportedResponse,
    dependencies=[Depends(require_permission("holding.add_asset"))],
)
async def check_fx_pair(
    quote_currency: str = Query(description="Asset currency — e.g. USD."),
    base_currency: str = Query(description="Portfolio currency — e.g. EUR."),
    current_user: User = Depends(get_current_user),
) -> FxPairSupportedResponse:
    """Check whether the FX pair is supported before adding an asset (D09 §8 step 2)."""
    svc = get_market_data_service()
    supported = await svc.is_fx_pair_supported(quote_currency.upper(), base_currency.upper())
    return FxPairSupportedResponse(
        quote_currency=quote_currency.upper(),
        base_currency=base_currency.upper(),
        supported=supported,
    )


@router.post(
    "/daily-update",
    response_model=DailyUpdateResponse,
    dependencies=[Depends(require_permission("system.run_jobs"))],
)
async def run_daily_update(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DailyUpdateResponse:
    """Manually trigger the daily price-fetch and alert-engine job (D09 §6).

    In production this will be scheduled via Celery beat (Spec D05).
    This endpoint is available for development, testing, and emergency manual runs.
    """
    svc = get_market_data_service()
    try:
        summary = await svc.run_daily_update(db)
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).exception("Daily update failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error en actualización diaria: {exc}",
        )
    return DailyUpdateResponse(
        assets_processed=summary["assets_processed"],
        assets_failed=summary["assets_failed"],
        alerts_triggered=summary["alerts_triggered"],
        indicator_snapshots=summary.get("indicator_snapshots", 0),
        ran_at=datetime.now(UTC),
    )
