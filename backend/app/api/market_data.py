"""D09 — Market & FX Data Integration API endpoints.

GET  /market-data/assets/search?q=       — live provider typeahead (D09 §8)
GET  /market-data/assets/{ticker}/price  — current price from active provider
GET  /market-data/fx/rate                — current FX rate, persisted to FxRateHistory
GET  /market-data/fx/supported           — check if a currency pair is supported
POST /market-data/daily-update           — trigger the daily price + alert job (D09 §6)
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d09_schemas import (
    AssetSearchResultResponse,
    DailyUpdateResponse,
    FxPairSupportedResponse,
    FxRateResponse,
    PricePointResponse,
)
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.market_data.service import get_market_data_service
from app.services.market_data.types import ProviderError

router = APIRouter(prefix="/market-data", tags=["market-data"])


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


@router.get("/assets/search", response_model=list[AssetSearchResultResponse])
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


@router.get("/assets/{ticker}/price", response_model=PricePointResponse)
async def get_asset_price(
    ticker: str,
    current_user: User = Depends(get_current_user),
) -> PricePointResponse:
    """Return the most recent available price for a ticker from the active provider."""
    svc = get_market_data_service()
    try:
        point = await svc.get_current_price(ticker.upper())
    except ProviderError as exc:
        raise _unavailable(exc)
    return PricePointResponse(
        ticker=ticker.upper(),
        as_of_date=point.as_of_date,
        price=point.price,
    )


@router.get("/fx/rate", response_model=FxRateResponse)
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


@router.get("/fx/supported", response_model=FxPairSupportedResponse)
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


@router.post("/daily-update", response_model=DailyUpdateResponse)
async def run_daily_update(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DailyUpdateResponse:
    """Manually trigger the daily price-fetch and alert-engine job (D09 §6).

    In production this will be scheduled via Celery beat (Spec D05).
    This endpoint is available for development, testing, and emergency manual runs.
    """
    svc = get_market_data_service()
    summary = await svc.run_daily_update(db)
    return DailyUpdateResponse(
        assets_processed=summary["assets_processed"],
        assets_failed=summary["assets_failed"],
        alerts_triggered=summary["alerts_triggered"],
        ran_at=datetime.now(UTC),
    )
