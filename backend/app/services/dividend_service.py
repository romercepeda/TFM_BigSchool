"""Dividend business logic — Spec D15.

Two independent concerns live in this module:
  - AssetDividendSchedule: asset-scoped, single-row upsert (D15 §3.1, §5.2),
    plus the DateAlert fan-out on save/delete (D15 §5.3) that reuses the
    existing DateAlert CRUD exactly as it stands — no new alert schema.
  - DividendPayment: holding-scoped CRUD (D15 §3.2, §6, §10), immutable
    except `notes`, mirroring sale_service.py's create/update_notes/delete shape.

compute_dividend_coverage_years() is a pure function (D15 §4) — no I/O — kept
here rather than in summary_service.py since it's specific to the dividend
domain; summary_service.py calls it after fetching its own inputs.
"""

from datetime import date as date_
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset
from app.db.models.date_alert import DateAlert
from app.db.models.dividend import AssetDividendSchedule, DividendPayment
from app.db.models.holding import Holding
from app.db.models.lot import Lot

_Q_MONETARY = Decimal("0.00000001")  # 8 dp, matches sale_service/summary_service's monetary precision
_Q_YEARS = Decimal("0.01")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

# D15 §5.3 — the fixed prefix that marks a DateAlert as system-generated from
# a dividend schedule, so it can be found again on the next edit without a
# new FK/column on DateAlert (explicit project-owner constraint: reuse the
# alert system exactly as it stands).
_ALERT_MARKER_PREFIX = "Dividendo: "

_PAYMENTS_PER_YEAR: dict[str, int] = {
    "monthly": 12,
    "quarterly": 4,
    "semiannual": 2,
    "annual": 1,
    # 'irregular' deliberately absent — no meaningful annualized run-rate (D15 §4.3).
}


def _round(value: Decimal) -> Decimal:
    return value.quantize(_Q_MONETARY, rounding=ROUND_HALF_EVEN)


# ── Pure computation (Spec D15 §4 — no I/O) ───────────────────────────────────


def compute_dividend_coverage_years(
    avg_purchase_price_base: Decimal,
    schedule: AssetDividendSchedule | None,
    fx_rate_current: Decimal | None,
    current_price_quote: Decimal | None = None,
) -> Decimal | None:
    """D15 §4.1 — years of the current annualized dividend needed to cover the
    average purchase price. None whenever the inputs don't support a
    meaningful estimate (no schedule, irregular frequency, zero/negative
    dividend or cost basis, unresolved current FX rate) — D15 §4.3.

    schedule.amount_type='percentage' (added post-v1) needs current_price_quote
    to convert the declared percentage into a nominal per-share amount before
    annualizing — None whenever that price isn't available either, same as
    fx_rate_current.
    """
    if schedule is None or fx_rate_current is None:
        return None
    if avg_purchase_price_base <= _ZERO:
        return None
    payments_per_year = _PAYMENTS_PER_YEAR.get(schedule.frequency)
    if payments_per_year is None:
        return None

    if schedule.amount_type == "percentage":
        if current_price_quote is None or current_price_quote <= _ZERO:
            return None
        amount_per_payment_quote = current_price_quote * (schedule.amount_per_payment / _HUNDRED)
    else:
        amount_per_payment_quote = schedule.amount_per_payment

    annualized_per_share_base = amount_per_payment_quote * payments_per_year * fx_rate_current
    if annualized_per_share_base <= _ZERO:
        return None

    return (avg_purchase_price_base / annualized_per_share_base).quantize(
        _Q_YEARS, rounding=ROUND_HALF_EVEN
    )


# ── AssetDividendSchedule CRUD (D15 §3.1, §5.2, §8.1) ─────────────────────────


async def get_schedule(db: AsyncSession, asset_id: UUID) -> AssetDividendSchedule | None:
    result = await db.execute(
        select(AssetDividendSchedule).where(AssetDividendSchedule.asset_id == asset_id)
    )
    return result.scalar_one_or_none()


async def get_schedules_for_assets(
    db: AsyncSession, asset_ids: set[UUID]
) -> dict[UUID, AssetDividendSchedule]:
    """Batch fetch, one query for every asset_id (D15 §4.4's list-row use case)."""
    if not asset_ids:
        return {}
    result = await db.execute(
        select(AssetDividendSchedule).where(AssetDividendSchedule.asset_id.in_(asset_ids))
    )
    return {s.asset_id: s for s in result.scalars().all()}


async def upsert_schedule(
    db: AsyncSession,
    asset: Asset,
    *,
    frequency: str,
    amount_type: str,
    amount_per_payment: Decimal,
    next_payment_date: date_ | None,
    notes: str | None,
) -> AssetDividendSchedule:
    """Create or overwrite the single schedule row for this asset (D15 §5.2,
    §3.1's single-current-row design — no history table). Caller must commit.

    Does not touch alerts by itself — call fan_out_schedule_alert() with the
    result, so the two concerns (persisting the schedule vs. reminding the
    user) stay independently testable, per D15 §5.3.
    """
    if amount_per_payment <= 0:
        raise ValueError("amount_per_payment must be greater than zero.")

    schedule = await get_schedule(db, asset.id)
    if schedule is None:
        schedule = AssetDividendSchedule(asset_id=asset.id, origin="manual")
        db.add(schedule)

    schedule.frequency = frequency
    schedule.amount_type = amount_type
    schedule.amount_per_payment = amount_per_payment
    schedule.next_payment_date = next_payment_date
    schedule.notes = notes
    await db.flush()
    return schedule


async def delete_schedule(db: AsyncSession, schedule: AssetDividendSchedule) -> None:
    await db.delete(schedule)
    await db.flush()


# ── DateAlert fan-out (D15 §5.3, §5.4) — reuses DateAlert exactly as-is ───────


async def _active_holdings_for_asset(db: AsyncSession, asset_id: UUID) -> list[Holding]:
    """Every holding (any user, any portfolio) referencing this asset with
    active_units > 0 — mirrors D06's asset-to-holdings fan-out already used
    for price-level crossing evaluation when a new price arrives for an asset.
    """
    result = await db.execute(
        select(Holding)
        .join(Lot, Lot.holding_id == Holding.id)
        .where(Holding.asset_id == asset_id)
        .group_by(Holding.id)
        .having(func.sum(Lot.quantity - Lot.quantity_consumed) > _ZERO)
    )
    return list(result.scalars().all())


def _marker(ticker: str) -> str:
    return f"{_ALERT_MARKER_PREFIX}{ticker}"


async def _find_marker_alert(db: AsyncSession, holding_id: UUID, ticker: str) -> DateAlert | None:
    result = await db.execute(
        select(DateAlert).where(
            DateAlert.holding_id == holding_id,
            DateAlert.description.like(f"{_marker(ticker)}%"),
        )
    )
    return result.scalar_one_or_none()


async def fan_out_schedule_alert(
    db: AsyncSession, asset: Asset, schedule: AssetDividendSchedule | None
) -> None:
    """Upsert (or remove) the marker DateAlert on every eligible holding of
    this asset (D15 §5.3). Called after upsert_schedule/delete_schedule.

    schedule=None, or a schedule with next_payment_date=None, removes any
    existing marker alert instead of creating/updating one. Caller must commit.
    """
    holdings = await _active_holdings_for_asset(db, asset.id)
    if not holdings:
        return

    for holding in holdings:
        alert = await _find_marker_alert(db, holding.id, asset.ticker)

        if schedule is None or schedule.next_payment_date is None:
            if alert is not None:
                await db.delete(alert)
            continue

        description = (
            f"{_marker(asset.ticker)} — {schedule.amount_per_payment}"
            f"{asset.quote_currency}/unidad"
        )
        if alert is None:
            db.add(DateAlert(
                holding_id=holding.id,
                alert_date=schedule.next_payment_date,
                description=description,
            ))
        else:
            alert.alert_date = schedule.next_payment_date
            alert.description = description

    await db.flush()


async def remove_dividend_alert(db: AsyncSession, holding_id: UUID, ticker: str) -> None:
    """Remove a holding's marker DateAlert (D15 §5.4) — called when a sale
    reduces the holding to active_units = 0, since a dividend reminder for
    shares no longer owned would be misleading. Caller must commit.
    """
    alert = await _find_marker_alert(db, holding_id, ticker)
    if alert is not None:
        await db.delete(alert)
        await db.flush()


# ── DividendPayment CRUD (D15 §3.2, §6.2, §6.3, §10) ──────────────────────────


async def get_payment(db: AsyncSession, payment_id: UUID, holding_id: UUID) -> DividendPayment | None:
    result = await db.execute(
        select(DividendPayment).where(
            DividendPayment.id == payment_id, DividendPayment.holding_id == holding_id
        )
    )
    return result.scalar_one_or_none()


async def list_payments_for_holding(db: AsyncSession, holding_id: UUID) -> list[DividendPayment]:
    result = await db.execute(
        select(DividendPayment)
        .where(DividendPayment.holding_id == holding_id)
        .order_by(DividendPayment.payment_date.desc())
    )
    return list(result.scalars().all())


async def create_payment(
    db: AsyncSession,
    holding_id: UUID,
    *,
    payment_date: date_,
    gross_amount_quote: Decimal,
    fx_rate_at_payment: Decimal | None,
    fx_rate_origin: str,
    notes: str | None,
) -> DividendPayment:
    """Register a received dividend payment (D15 §6.2). Caller must commit.

    Raises ValueError if gross_amount_quote is not > 0, or if fx_rate_at_payment
    is missing while fx_rate_origin isn't 'manual_pending' (same contract as
    sale_service.create_sale / lot_service.add_lot).
    """
    if gross_amount_quote <= 0:
        raise ValueError("gross_amount_quote must be greater than zero.")
    if fx_rate_origin != "manual_pending" and fx_rate_at_payment is None:
        raise ValueError(
            "fx_rate_at_payment is required unless fx_rate_origin is 'manual_pending'."
        )

    gross_amount_base = (
        _round(gross_amount_quote * fx_rate_at_payment)
        if fx_rate_at_payment is not None else None
    )

    payment = DividendPayment(
        holding_id=holding_id,
        payment_date=payment_date,
        gross_amount_quote=gross_amount_quote,
        fx_rate_at_payment=fx_rate_at_payment,
        fx_rate_origin=fx_rate_origin,
        gross_amount_base=gross_amount_base,
        notes=notes,
    )
    db.add(payment)
    await db.flush()
    return payment


async def update_notes(db: AsyncSession, payment: DividendPayment, notes: str | None) -> DividendPayment:
    """Edit only a payment's notes (D15 §10) — every other field is locked
    once the payment is created. Caller must commit."""
    payment.notes = notes
    await db.flush()
    return payment


async def delete_payment(db: AsyncSession, payment: DividendPayment) -> None:
    await db.delete(payment)
    await db.flush()


async def get_active_units(db: AsyncSession, holding_id: UUID) -> Decimal:
    """Current active_units for one holding — used by the create-sale endpoint
    to decide whether to remove the holding's dividend alert (D15 §5.4).
    """
    result = await db.execute(
        select(func.sum(Lot.quantity - Lot.quantity_consumed)).where(Lot.holding_id == holding_id)
    )
    total = result.scalar_one_or_none()
    return total if total is not None else _ZERO
