"""D05 — Indicator Catalog & Historical Snapshots API endpoints.

GET /indicators                           — list all active indicators
GET /assets/{asset_id}/indicators         — asset-level snapshots (current + last 2)
GET /portfolios/{portfolio_id}/indicators — portfolio KPIs (on-demand, v1: no stored snapshots)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d05_schemas import IndicatorOut, IndicatorSnapshotHistoryOut, SnapshotOut
from app.auth.dependencies import get_current_user
from app.db.models.holding import Holding
from app.db.models.indicator import Indicator
from app.db.models.portfolio import Portfolio
from app.db.models.user import User
from app.db.session import get_db
from app.services.indicator_service import (
    get_asset_indicator_history,
    get_indicators_by_scope,
)

router = APIRouter(tags=["indicators"])


@router.get("/indicators", response_model=list[IndicatorOut])
async def list_indicators(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IndicatorOut]:
    """Return all active indicator catalog entries (D05 §3)."""
    asset_indicators = await get_indicators_by_scope(db, "asset")
    portfolio_indicators = await get_indicators_by_scope(db, "portfolio")
    all_indicators = asset_indicators + portfolio_indicators
    return [IndicatorOut.model_validate(i) for i in all_indicators]


@router.get(
    "/assets/{asset_id}/indicators",
    response_model=list[IndicatorSnapshotHistoryOut],
)
async def get_asset_indicators(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IndicatorSnapshotHistoryOut]:
    """Return current + last 2 snapshots for all asset-level indicators (D05 §7).

    Authorization: the requesting user must own at least one holding of this asset
    across any of their portfolios (D05 §9).
    """
    holding_exists = await db.scalar(
        select(Holding)
        .join(Portfolio, Portfolio.id == Holding.portfolio_id)
        .where(
            Holding.asset_id == asset_id,
            Portfolio.user_id == current_user.id,
        )
        .limit(1)
    )
    if holding_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found or not in your portfolios.",
        )

    indicators = await get_indicators_by_scope(db, "asset")
    result = []
    for indicator in indicators:
        history = await get_asset_indicator_history(db, asset_id, indicator)
        result.append(
            IndicatorSnapshotHistoryOut(
                indicator=IndicatorOut.model_validate(indicator),
                snapshots=[SnapshotOut(**s) for s in history],
            )
        )
    return result


@router.get(
    "/portfolios/{portfolio_id}/indicators",
    response_model=list[IndicatorSnapshotHistoryOut],
)
async def get_portfolio_indicators(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IndicatorSnapshotHistoryOut]:
    """Return portfolio KPI definitions for the given portfolio (D05 §6.3).

    In v1, portfolio KPIs have on_demand_calculated strategy: no snapshots are persisted
    and the response always contains an empty snapshots list. Actual computation is
    out of scope for v1 (D05 §10).
    """
    portfolio = await db.scalar(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    indicators = await get_indicators_by_scope(db, "portfolio")
    return [
        IndicatorSnapshotHistoryOut(
            indicator=IndicatorOut.model_validate(ind),
            snapshots=[],
        )
        for ind in indicators
    ]
