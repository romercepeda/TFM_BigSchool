"""D04 — FX Calculation Engine API endpoint (Spec D04).

POST /portfolios/{portfolio_id}/holdings/{holding_id}/calculate
    Body: { current_unit_price?, fx_rate_current? }
    Returns: HoldingCalcResponse with per-lot and aggregated FX metrics.

With D09 implemented, both body fields are optional.  If omitted, the server
resolves them automatically via the market data service:
  - current_unit_price  ← fetched from the active market data provider
  - fx_rate_current     ← fetched from Frankfurter and persisted to FxRateHistory

Supply either field explicitly to override the auto-resolved value.
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
from app.services.market_data.service import get_market_data_service
from app.services.market_data.types import ProviderError
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

    Omit current_unit_price and/or fx_rate_current to auto-resolve from D09.
    Provide them explicitly to override (manual mode or testing).
    """
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND

    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id, Holding.portfolio_id == portfolio_id)
        .options(selectinload(Holding.lots), selectinload(Holding.asset))
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise _NOT_FOUND

    svc = get_market_data_service()

    # ── Resolve current_unit_price ────────────────────────────────────────────
    current_price = body.current_unit_price
    if current_price is None:
        try:
            point = await svc.get_current_price(holding.asset.ticker)
            current_price = point.price
        except ProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Datos no disponibles — no se pudo obtener el precio actual.",
                    "error_kind": exc.error_kind,
                    "retryable": exc.retryable,
                    "upstream": exc.upstream_message,
                },
            )

    # ── Resolve fx_rate_current ───────────────────────────────────────────────
    fx_rate = body.fx_rate_current
    if fx_rate is None:
        try:
            fx_rate = await svc.get_current_fx_rate(
                db,
                quote=holding.asset.quote_currency,
                base=portfolio.base_currency,
            )
            await db.commit()
        except ProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "message": "Datos no disponibles — no se pudo obtener el tipo de cambio actual.",
                    "error_kind": exc.error_kind,
                    "retryable": exc.retryable,
                    "upstream": exc.upstream_message,
                },
            )

    lot_inputs = [
        LotCalcInput(
            lot_id=lot.id,
            quantity_remaining=lot.quantity_remaining,
            unit_price_at_purchase=lot.unit_price,
            fx_rate_at_purchase=lot.fx_rate_at_purchase,
            current_unit_price=current_price,
            fx_rate_current=fx_rate,
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
