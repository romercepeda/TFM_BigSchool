"""D05 — Indicator Catalog & Historical Snapshots API endpoints.

GET /indicators                           — list all active indicators
GET /assets/{asset_id}/indicators         — asset-level snapshots (current + last 2)
GET /portfolios/{portfolio_id}/indicators — portfolio KPIs (on-demand, v1: no stored snapshots)

D08: all responses include translated indicator names (IndicatorOut.name) and
translated state labels (SnapshotOut.value_text_display) based on the user's
preferred_language.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d05_schemas import IndicatorOut, IndicatorSnapshotHistoryOut, SnapshotOut
from app.auth.dependencies import get_current_user
from app.config import get_config
from app.db.models.holding import Holding
from app.db.models.indicator import Indicator
from app.db.models.portfolio import Portfolio
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services.i18n_service import translate_indicator_name, translate_state
from app.services.indicator_service import (
    get_asset_indicator_history,
    get_indicators_by_scope,
)

router = APIRouter(tags=["indicators"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_indicator_out(indicator: Indicator, lang: str, default_lang: str) -> IndicatorOut:
    """Construct an IndicatorOut with the translated name field set."""
    out = IndicatorOut.model_validate(indicator)
    return out.model_copy(
        update={"name": translate_indicator_name(indicator.name_key, lang, default_lang)}
    )


def _build_snapshot_out(
    snapshot_dict: dict,
    indicator: Indicator,
    lang: str,
    default_lang: str,
) -> SnapshotOut:
    """Construct a SnapshotOut with value_text_display set for qualitative indicators."""
    out = SnapshotOut(**snapshot_dict)
    if indicator.data_type == "qualitative" and out.value_text:
        out = out.model_copy(
            update={
                "value_text_display": translate_state(
                    indicator.code, out.value_text, lang, default_lang
                )
            }
        )
    return out


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/indicators",
    response_model=list[IndicatorOut],
    dependencies=[Depends(require_permission("holding.view"))],
)
async def list_indicators(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IndicatorOut]:
    """Return all active indicator catalog entries (D05 §3), names translated."""
    cfg = get_config()
    lang = current_user.preferred_language
    default_lang = cfg.i18n.default_language

    asset_indicators = await get_indicators_by_scope(db, "asset")
    portfolio_indicators = await get_indicators_by_scope(db, "portfolio")
    all_indicators = asset_indicators + portfolio_indicators
    return [_build_indicator_out(i, lang, default_lang) for i in all_indicators]


@router.get(
    "/assets/{asset_id}/indicators",
    response_model=list[IndicatorSnapshotHistoryOut],
    dependencies=[Depends(require_permission("holding.view"))],
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

    cfg = get_config()
    lang = current_user.preferred_language
    default_lang = cfg.i18n.default_language

    indicators = await get_indicators_by_scope(db, "asset")
    result = []
    for indicator in indicators:
        history = await get_asset_indicator_history(db, asset_id, indicator)
        result.append(
            IndicatorSnapshotHistoryOut(
                indicator=_build_indicator_out(indicator, lang, default_lang),
                snapshots=[
                    _build_snapshot_out(s, indicator, lang, default_lang)
                    for s in history
                ],
            )
        )
    return result


@router.get(
    "/portfolios/{portfolio_id}/indicators",
    response_model=list[IndicatorSnapshotHistoryOut],
    dependencies=[Depends(require_permission("portfolio.list"))],
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

    cfg = get_config()
    lang = current_user.preferred_language
    default_lang = cfg.i18n.default_language

    indicators = await get_indicators_by_scope(db, "portfolio")
    return [
        IndicatorSnapshotHistoryOut(
            indicator=_build_indicator_out(ind, lang, default_lang),
            snapshots=[],
        )
        for ind in indicators
    ]
