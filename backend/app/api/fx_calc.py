"""D04 — FX Calculation Engine API endpoints (Spec D04).

POST /portfolios/{portfolio_id}/holdings/{holding_id}/calculate
    Body: { current_unit_price, fx_rate_current }
    Returns: HoldingCalcResponse with per-lot and aggregated FX metrics.

The engine is pure and stateless: it does not fetch market data. The caller
supplies the current price and FX rate. When D09 (market-data integration) is
implemented, these values will be resolved automatically; this endpoint remains
available for manual overrides and testing.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.d04_schemas import FxCalcRequest, HoldingCalcResponse, LotCalcResponse
from app.auth.dependencies import get_current_user
from app.db.models.holding import Holding
from app.db.models.user import User
from app.db.session import get_db
from app.services import fx_engine
from app.services.fx_engine import LotCalcInput
from app.services.portfolio_service import get_portfolio_by_id

router = APIRouter(prefix="/portfolios", tags=["fx-calc"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found."
)


@router.post(
    "/{portfolio_id}/holdings/{holding_id}/calculate",
    response_model=HoldingCalcResponse,
    summary="Calculate FX metrics for a holding (Spec D04)",
)
async def calculate_holding_fx(
    portfolio_id: UUID,
    holding_id: UUID,
    body: FxCalcRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HoldingCalcResponse:
    """Return asset_return, base_return, and fx_effect per lot and aggregated.

    current_unit_price and fx_rate_current are caller-supplied (D09 will
    resolve these automatically in a future iteration).
    """
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND

    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id, Holding.portfolio_id == portfolio_id)
        .options(selectinload(Holding.lots))
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise _NOT_FOUND

    lot_inputs = [
        LotCalcInput(
            lot_id=lot.id,
            quantity_remaining=lot.quantity_remaining,
            unit_price_at_purchase=lot.unit_price,
            fx_rate_at_purchase=lot.fx_rate_at_purchase,
            current_unit_price=body.current_unit_price,
            fx_rate_current=body.fx_rate_current,
        )
        for lot in holding.lots
    ]

    calc = fx_engine.calculate_holding(lot_inputs)

    return HoldingCalcResponse(
        holding_id=holding_id,
        has_fx_missing=calc.has_fx_missing,
        total_cost_quote=calc.total_cost_quote,
        total_cost_base=calc.total_cost_base,
        total_value_quote=calc.total_value_quote,
        total_value_base=calc.total_value_base,
        asset_return_total=calc.asset_return_total,
        base_return_total=calc.base_return_total,
        fx_effect_total=calc.fx_effect_total,
        lots=[
            LotCalcResponse(
                lot_id=r.lot_id,
                status=r.status,
                cost_quote=r.cost_quote,
                cost_base=r.cost_base,
                current_value_quote=r.current_value_quote,
                current_value_base=r.current_value_base,
                asset_return=r.asset_return,
                base_return=r.base_return,
                fx_effect=r.fx_effect,
            )
            for r in calc.lot_results
        ],
    )
