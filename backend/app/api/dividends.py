"""Dividend Tracking API endpoints — Spec D15.

Two routers, reflecting the two different scopes of the two entities (D15 §3):

    GET/PUT/DELETE /assets/{asset_id}/dividend-schedule
        — asset-scoped (shared reference data, like PATCH /assets/{id}).
          No portfolio-ownership check: any authenticated user holding this
          asset can view/edit its declared schedule, same shared-data model
          already accepted for asset metadata (D15 §8.1).

    GET/POST    /portfolios/{pid}/holdings/{hid}/dividend-payments
    PATCH/DELETE /portfolios/{pid}/holdings/{hid}/dividend-payments/{id}
        — holding-scoped (personal cash-flow record), nested under
          portfolios/holdings to reuse the existing ownership check, mirroring
          date_alerts.py and the sales endpoints in holdings.py.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dividend_schemas import (
    DividendPaymentIn,
    DividendPaymentPatch,
    DividendPaymentResponse,
    DividendScheduleIn,
    DividendScheduleResponse,
)
from app.api.holdings import _resolve_fx_rate
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services import asset_service, dividend_service, lot_service, summary_cache
from app.services.portfolio_service import get_portfolio_by_id

schedule_router = APIRouter(prefix="/assets/{asset_id}/dividend-schedule", tags=["dividends"])
payments_router = APIRouter(
    prefix="/portfolios/{portfolio_id}/holdings/{holding_id}/dividend-payments",
    tags=["dividends"],
)

_NOT_FOUND_ASSET = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
_NOT_FOUND_SCHEDULE = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="No dividend schedule declared for this asset."
)
_NOT_FOUND_PORTFOLIO = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")
_NOT_FOUND_HOLDING = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")
_NOT_FOUND_PAYMENT = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Dividend payment not found."
)


def _bad_request(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── AssetDividendSchedule endpoints (D15 §8.1) ────────────────────────────────


@schedule_router.get(
    "",
    response_model=DividendScheduleResponse,
    dependencies=[Depends(require_permission("dividend.schedule.view"))],
)
async def get_dividend_schedule(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DividendScheduleResponse:
    asset = await asset_service.get_asset_by_id(db, asset_id)
    if asset is None:
        raise _NOT_FOUND_ASSET
    schedule = await dividend_service.get_schedule(db, asset_id)
    if schedule is None:
        raise _NOT_FOUND_SCHEDULE
    return DividendScheduleResponse.model_validate(schedule)


@schedule_router.put(
    "",
    response_model=DividendScheduleResponse,
    dependencies=[Depends(require_permission("dividend.schedule.edit"))],
)
async def upsert_dividend_schedule(
    asset_id: UUID,
    body: DividendScheduleIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DividendScheduleResponse:
    """Create or overwrite the declared dividend schedule for this asset
    (D15 §5.2). Triggers the DateAlert fan-out (D15 §5.3) on every active
    holding of this asset when next_payment_date is set.
    """
    asset = await asset_service.get_asset_by_id(db, asset_id)
    if asset is None:
        raise _NOT_FOUND_ASSET

    try:
        schedule = await dividend_service.upsert_schedule(
            db, asset,
            frequency=body.frequency,
            amount_type=body.amount_type,
            amount_per_payment=body.amount_per_payment,
            next_payment_date=body.next_payment_date,
            notes=body.notes,
        )
    except ValueError as exc:
        raise _bad_request(str(exc))

    await dividend_service.fan_out_schedule_alert(db, asset, schedule)
    await db.commit()
    await db.refresh(schedule)
    return DividendScheduleResponse.model_validate(schedule)


@schedule_router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("dividend.schedule.edit"))],
)
async def delete_dividend_schedule(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    asset = await asset_service.get_asset_by_id(db, asset_id)
    if asset is None:
        raise _NOT_FOUND_ASSET
    schedule = await dividend_service.get_schedule(db, asset_id)
    if schedule is None:
        raise _NOT_FOUND_SCHEDULE

    await dividend_service.delete_schedule(db, schedule)
    await dividend_service.fan_out_schedule_alert(db, asset, None)
    await db.commit()


# ── DividendPayment endpoints (D15 §8.2) ──────────────────────────────────────


async def _require_holding(portfolio_id: UUID, holding_id: UUID, current_user: User, db: AsyncSession):
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND_PORTFOLIO
    holding = await lot_service.get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING
    return portfolio, holding


@payments_router.get(
    "",
    response_model=list[DividendPaymentResponse],
    dependencies=[Depends(require_permission("dividend.payment.view"))],
)
async def list_dividend_payments(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DividendPaymentResponse]:
    await _require_holding(portfolio_id, holding_id, current_user, db)
    payments = await dividend_service.list_payments_for_holding(db, holding_id)
    return [DividendPaymentResponse.model_validate(p) for p in payments]


@payments_router.post(
    "",
    response_model=DividendPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("dividend.payment.create"))],
)
async def create_dividend_payment(
    portfolio_id: UUID,
    holding_id: UUID,
    body: DividendPaymentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DividendPaymentResponse:
    """Register a received dividend payment (D15 §6.2). Set fx_rate_origin='auto'
    to have the FX rate resolved from Frankfurter, same as lots/sales.
    """
    portfolio, holding = await _require_holding(portfolio_id, holding_id, current_user, db)

    fx_rate, fx_origin = await _resolve_fx_rate(
        db,
        quote_currency=holding.asset.quote_currency,
        base_currency=portfolio.base_currency,
        on_date=body.payment_date,
        requested_origin=body.fx_rate_origin,
        provided_rate=body.fx_rate_at_payment,
    )

    try:
        payment = await dividend_service.create_payment(
            db, holding_id,
            payment_date=body.payment_date,
            gross_amount_quote=body.gross_amount_quote,
            fx_rate_at_payment=fx_rate,
            fx_rate_origin=fx_origin,
            notes=body.notes,
        )
    except ValueError as exc:
        raise _bad_request(str(exc))

    await db.commit()
    summary_cache.invalidate(portfolio_id)
    await db.refresh(payment)
    return DividendPaymentResponse.model_validate(payment)


@payments_router.patch(
    "/{payment_id}",
    response_model=DividendPaymentResponse,
    dependencies=[Depends(require_permission("dividend.payment.edit_notes"))],
)
async def update_dividend_payment_notes(
    portfolio_id: UUID,
    holding_id: UUID,
    payment_id: UUID,
    body: DividendPaymentPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DividendPaymentResponse:
    """Edit a payment's notes. Every other field is immutable (D15 §10).
    Does not invalidate the portfolio summary cache — a notes edit has no
    financial impact, same rule as Sale's reason edit (D13 §8.1).
    """
    await _require_holding(portfolio_id, holding_id, current_user, db)
    payment = await dividend_service.get_payment(db, payment_id, holding_id)
    if payment is None:
        raise _NOT_FOUND_PAYMENT

    payment = await dividend_service.update_notes(db, payment, body.notes)
    await db.commit()
    await db.refresh(payment)
    return DividendPaymentResponse.model_validate(payment)


@payments_router.delete(
    "/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("dividend.payment.delete"))],
)
async def delete_dividend_payment(
    portfolio_id: UUID,
    holding_id: UUID,
    payment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_holding(portfolio_id, holding_id, current_user, db)
    payment = await dividend_service.get_payment(db, payment_id, holding_id)
    if payment is None:
        raise _NOT_FOUND_PAYMENT

    await dividend_service.delete_payment(db, payment)
    await db.commit()
    summary_cache.invalidate(portfolio_id)
