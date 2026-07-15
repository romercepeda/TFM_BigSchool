"""Holdings, Lots, and Sales API endpoints — Spec D03, sales extended by Spec D13.

All routes are nested under /portfolios/{portfolio_id}/ to enforce portfolio ownership.
Authorization: every handler verifies the portfolio belongs to the current user before
accessing any child entity. Users cannot reach holdings in portfolios they do not own.

Endpoints:
    GET    /portfolios/{pid}/holdings                       — list holdings with aggregates
    POST   /portfolios/{pid}/holdings                       — add asset + first lot (atomic)
    GET    /portfolios/{pid}/holdings/{hid}                 — detail: asset, lots, sales
    DELETE /portfolios/{pid}/holdings/{hid}                 — delete holding + all child records
    POST   /portfolios/{pid}/holdings/{hid}/lots            — add another lot
    PATCH  /portfolios/{pid}/holdings/{hid}/lots/{lid}      — edit lot
    DELETE /portfolios/{pid}/holdings/{hid}/lots/{lid}      — delete lot (blocks if consumed)
    POST   /portfolios/{pid}/holdings/{hid}/sales           — register sale (FIFO, realized gain)
    PATCH  /portfolios/{pid}/holdings/{hid}/sales/{sid}     — edit sale reason only (D13 §11)
    DELETE /portfolios/{pid}/holdings/{hid}/sales/{sid}     — delete sale (restores FIFO)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d03_schemas import (
    CreateHoldingRequest,
    HoldingAggregates,
    HoldingDetailResponse,
    HoldingSummaryResponse,
    LotIn,
    LotPatch,
    LotResponse,
    SaleIn,
    SalePatch,
    SaleResponse,
)
from app.auth.dependencies import get_current_user
from app.db.models.holding import Holding
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services import asset_service, lot_service, sale_service, summary_cache
from app.services.market_data.service import get_market_data_service
from app.services.portfolio_service import get_portfolio_by_id

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["holdings"])


async def _resolve_fx_rate(
    db,
    quote_currency: str,
    base_currency: str,
    on_date,
    requested_origin: str,
    provided_rate,
):
    """If fx_rate_origin='auto' and no rate was provided, auto-fetch from D09.

    Returns (resolved_rate, resolved_origin). On fetch failure falls back to
    (None, 'manual_pending') per D09 §7.1.
    """
    if requested_origin != "auto" or provided_rate is not None:
        return provided_rate, requested_origin

    from app.services.market_data.types import ProviderError
    svc = get_market_data_service()
    rate = await svc.get_historical_fx_rate(db, quote_currency, base_currency, on_date)
    if rate is not None:
        return rate, "auto"
    return None, "manual_pending"

_NOT_FOUND_PORTFOLIO = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found."
)
_NOT_FOUND_HOLDING = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found."
)
_NOT_FOUND_LOT = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Lot not found."
)
_NOT_FOUND_SALE = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found."
)


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


def _bad_request(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


async def _require_portfolio(
    portfolio_id: UUID,
    current_user: User,
    db: AsyncSession,
):
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND_PORTFOLIO
    return portfolio


def _build_aggregates(holding: Holding) -> HoldingAggregates:
    agg = lot_service.compute_holding_aggregates(holding.lots)
    return HoldingAggregates(**agg)


# ── Holding endpoints ─────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[HoldingSummaryResponse],
    dependencies=[Depends(require_permission("holding.view"))],
)
async def list_holdings(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HoldingSummaryResponse]:
    """List all holdings in a portfolio with computed aggregates."""
    await _require_portfolio(portfolio_id, current_user, db)
    holdings = await lot_service.list_holdings(db, portfolio_id)

    results = []
    for h in holdings:
        # Load lots for aggregate computation (list_holdings eager-loads asset only).
        detail = await lot_service.get_holding_detail(db, h.id, portfolio_id)
        if detail is None:
            continue
        results.append(HoldingSummaryResponse(
            id=detail.id,
            asset=detail.asset,
            lot_count=len(detail.lots),
            sale_count=len(detail.sales),
            aggregates=_build_aggregates(detail),
            created_at=detail.created_at,
            updated_at=detail.updated_at,
        ))
    return results


@router.post(
    "",
    response_model=HoldingDetailResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("holding.add_asset"))],
)
async def add_holding(
    portfolio_id: UUID,
    body: CreateHoldingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingDetailResponse:
    """Add an asset to a portfolio with its first lot. Atomic: all-or-nothing.

    If the asset ticker already exists, the existing Asset record is reused.
    Set lot.fx_rate_origin='auto' to have the FX rate resolved from Frankfurter.
    Returns 409 if the asset is already in this portfolio (use POST .../lots to add more).
    """
    portfolio = await _require_portfolio(portfolio_id, current_user, db)

    asset, _ = await asset_service.get_or_create_asset(
        db,
        ticker=body.asset.ticker,
        name=body.asset.name,
        asset_type=body.asset.asset_type,
        quote_currency=body.asset.quote_currency,
        market=body.asset.market,
    )

    # Check uniqueness: one holding per (portfolio, asset) pair.
    from sqlalchemy import select
    from app.db.models.holding import Holding as HoldingModel
    existing = await db.execute(
        select(HoldingModel).where(
            HoldingModel.portfolio_id == portfolio_id,
            HoldingModel.asset_id == asset.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise _conflict(
            f"{body.asset.ticker.upper()} is already in this portfolio. "
            "Use POST .../lots to add another purchase lot."
        )

    holding = Holding(portfolio_id=portfolio_id, asset_id=asset.id)
    db.add(holding)
    await db.flush()

    fx_rate, fx_origin = await _resolve_fx_rate(
        db,
        quote_currency=asset.quote_currency,
        base_currency=portfolio.base_currency,
        on_date=body.lot.purchase_date,
        requested_origin=body.lot.fx_rate_origin,
        provided_rate=body.lot.fx_rate_at_purchase,
    )

    try:
        await lot_service.add_lot(
            db, holding,
            purchase_date=body.lot.purchase_date,
            quantity=body.lot.quantity,
            unit_price=body.lot.unit_price,
            fx_rate_at_purchase=fx_rate,
            fx_rate_origin=fx_origin,
            notes=body.lot.notes,
        )
    except ValueError as exc:
        raise _bad_request(str(exc))

    await db.commit()
    summary_cache.invalidate(portfolio_id)
    detail = await lot_service.get_holding_detail(db, holding.id, portfolio_id)
    return HoldingDetailResponse(
        id=detail.id,
        asset=detail.asset,
        lots=detail.lots,
        sales=detail.sales,
        aggregates=_build_aggregates(detail),
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )


@router.get(
    "/{holding_id}",
    response_model=HoldingDetailResponse,
    dependencies=[Depends(require_permission("holding.view"))],
)
async def get_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingDetailResponse:
    """Return holding detail: asset info, all lots, all sales with FIFO breakdown."""
    await _require_portfolio(portfolio_id, current_user, db)
    detail = await lot_service.get_holding_detail(db, holding_id, portfolio_id)
    if detail is None:
        raise _NOT_FOUND_HOLDING
    return HoldingDetailResponse(
        id=detail.id,
        asset=detail.asset,
        lots=detail.lots,
        sales=detail.sales,
        aggregates=_build_aggregates(detail),
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )


@router.delete(
    "/{holding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("holding.delete"))],
)
async def delete_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a holding and all its lots, sales, and price levels."""
    await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_detail(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING
    await db.delete(holding)
    await db.commit()
    summary_cache.invalidate(portfolio_id)


# ── Lot endpoints ─────────────────────────────────────────────────────────────


@router.post(
    "/{holding_id}/lots",
    response_model=LotResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("lot.create"))],
)
async def add_lot(
    portfolio_id: UUID,
    holding_id: UUID,
    body: LotIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotResponse:
    """Add a purchase lot to an existing holding.

    Set fx_rate_origin='auto' to have the FX rate resolved from Frankfurter.
    """
    portfolio = await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING

    fx_rate, fx_origin = await _resolve_fx_rate(
        db,
        quote_currency=holding.asset.quote_currency,
        base_currency=portfolio.base_currency,
        on_date=body.purchase_date,
        requested_origin=body.fx_rate_origin,
        provided_rate=body.fx_rate_at_purchase,
    )

    try:
        lot = await lot_service.add_lot(
            db, holding,
            purchase_date=body.purchase_date,
            quantity=body.quantity,
            unit_price=body.unit_price,
            fx_rate_at_purchase=fx_rate,
            fx_rate_origin=fx_origin,
            notes=body.notes,
        )
    except ValueError as exc:
        raise _bad_request(str(exc))

    await db.commit()
    summary_cache.invalidate(portfolio_id)
    await db.refresh(lot)
    return LotResponse.model_validate(lot)


@router.patch(
    "/{holding_id}/lots/{lot_id}",
    response_model=LotResponse,
    dependencies=[Depends(require_permission("lot.edit"))],
)
async def edit_lot(
    portfolio_id: UUID,
    holding_id: UUID,
    lot_id: UUID,
    body: LotPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LotResponse:
    """Edit an unconsumed lot. Returns 409 if the lot has been consumed by sales."""
    await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING

    lot = await lot_service.get_lot(db, lot_id, holding_id)
    if lot is None:
        raise _NOT_FOUND_LOT

    try:
        lot = await lot_service.edit_lot(
            db, lot,
            purchase_date=body.purchase_date,
            quantity=body.quantity,
            unit_price=body.unit_price,
            fx_rate_at_purchase=body.fx_rate_at_purchase,
            fx_rate_origin=body.fx_rate_origin,
            notes=body.notes,
        )
    except ValueError as exc:
        raise _conflict(str(exc))

    await db.commit()
    summary_cache.invalidate(portfolio_id)
    await db.refresh(lot)
    return LotResponse.model_validate(lot)


@router.delete(
    "/{holding_id}/lots/{lot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("lot.delete"))],
)
async def delete_lot(
    portfolio_id: UUID,
    holding_id: UUID,
    lot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a lot. Returns 409 if consumed by sales.

    The holding is preserved even if this was its last remaining lot.
    """
    await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING

    lot = await lot_service.get_lot(db, lot_id, holding_id)
    if lot is None:
        raise _NOT_FOUND_LOT

    try:
        await lot_service.delete_lot(db, lot)
    except ValueError as exc:
        raise _conflict(str(exc))

    await db.commit()
    summary_cache.invalidate(portfolio_id)


# ── Sale endpoints ────────────────────────────────────────────────────────────


@router.post(
    "/{holding_id}/sales",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("sale.create"))],
)
async def create_sale(
    portfolio_id: UUID,
    holding_id: UUID,
    body: SaleIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SaleResponse:
    """Register a sale. FIFO lot consumption is applied atomically.

    Set fx_rate_origin='auto' to have the FX rate resolved from Frankfurter.
    """
    portfolio = await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING

    fx_rate, fx_origin = await _resolve_fx_rate(
        db,
        quote_currency=holding.asset.quote_currency,
        base_currency=portfolio.base_currency,
        on_date=body.sale_date,
        requested_origin=body.fx_rate_origin,
        provided_rate=body.fx_rate_at_sale,
    )

    try:
        sale = await sale_service.create_sale(
            db, holding_id,
            sale_date=body.sale_date,
            quantity=body.quantity,
            unit_price=body.unit_price,
            fx_rate_at_sale=fx_rate,
            fx_rate_origin=fx_origin,
            notes=body.notes,
        )
    except ValueError as exc:
        raise _bad_request(str(exc))

    await db.commit()
    summary_cache.invalidate(portfolio_id)
    await db.refresh(sale)
    # Reload with lot_consumptions eager-loaded.
    sale_detail = await sale_service.get_sale(db, sale.id, holding_id)
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.db.models.sale import Sale as SaleModel
    result = await db.execute(
        select(SaleModel)
        .where(SaleModel.id == sale.id)
        .options(selectinload(SaleModel.lot_consumptions))
    )
    sale = result.scalar_one()
    return SaleResponse.model_validate(sale)


@router.patch(
    "/{holding_id}/sales/{sale_id}",
    response_model=SaleResponse,
    dependencies=[Depends(require_permission("sale.edit_reason"))],
)
async def update_sale_reason(
    portfolio_id: UUID,
    holding_id: UUID,
    sale_id: UUID,
    body: SalePatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SaleResponse:
    """Edit a sale's reason. Every other field is immutable (Spec D13 §11).

    Does not invalidate the portfolio summary cache — a reason edit has no
    financial impact (D13 §8.1).
    """
    await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING

    sale = await sale_service.get_sale(db, sale_id, holding_id)
    if sale is None:
        raise _NOT_FOUND_SALE

    sale = await sale_service.update_reason(db, sale, body.notes)
    await db.commit()

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.db.models.sale import Sale as SaleModel
    result = await db.execute(
        select(SaleModel)
        .where(SaleModel.id == sale.id)
        .options(selectinload(SaleModel.lot_consumptions))
    )
    sale = result.scalar_one()
    return SaleResponse.model_validate(sale)


@router.delete(
    "/{holding_id}/sales/{sale_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("sale.delete"))],
)
async def delete_sale(
    portfolio_id: UUID,
    holding_id: UUID,
    sale_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a sale and restore consumed lot quantities."""
    await _require_portfolio(portfolio_id, current_user, db)
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING

    sale = await sale_service.get_sale(db, sale_id, holding_id)
    if sale is None:
        raise _NOT_FOUND_SALE

    await sale_service.delete_sale(db, sale)
    await db.commit()
    summary_cache.invalidate(portfolio_id)
