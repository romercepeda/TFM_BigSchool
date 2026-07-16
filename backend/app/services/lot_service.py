"""Lot business logic — create, edit, delete, holding aggregates.

Rules enforced here (Spec D03 §6):
  - quantity and unit_price must be > 0.
  - A lot with quantity_consumed > 0 cannot be edited or deleted (consumed rule §6.2).
  - The parent holding is preserved even when its last lot is deleted (§6.3); it is
    only removed via the explicit "delete asset" action.
  - Aggregated holding views (§8) are computed here from lot data.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.asset import Asset
from app.db.models.holding import Holding
from app.db.models.lot import Lot
from app.db.models.sale import Sale, SaleLotConsumption


# ── Internal helpers ─────────────────────────────────────────────────────────


async def get_holding_with_asset(
    db: AsyncSession, holding_id: UUID, portfolio_id: UUID
) -> Holding | None:
    """Return a holding (with asset eagerly loaded) that belongs to this portfolio."""
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id, Holding.portfolio_id == portfolio_id)
        .options(selectinload(Holding.asset))
    )
    return result.scalar_one_or_none()


async def get_lot(db: AsyncSession, lot_id: UUID, holding_id: UUID) -> Lot | None:
    result = await db.execute(
        select(Lot).where(Lot.id == lot_id, Lot.holding_id == holding_id)
    )
    return result.scalar_one_or_none()


# ── Holding queries ───────────────────────────────────────────────────────────


async def list_holdings(db: AsyncSession, portfolio_id: UUID) -> list[Holding]:
    """Return all holdings for a portfolio with asset eager-loaded."""
    result = await db.execute(
        select(Holding)
        .where(Holding.portfolio_id == portfolio_id)
        .options(selectinload(Holding.asset))
        .order_by(Holding.created_at.asc())
    )
    return list(result.scalars().all())


async def get_holding_detail(
    db: AsyncSession, holding_id: UUID, portfolio_id: UUID
) -> Holding | None:
    """Return a holding with asset, lots, and sales eagerly loaded.

    Each sale's consumptions also eager-load their Lot (D13 §6.1's FIFO
    breakdown reads purchase_date/unit_price/cost_contribution off
    SaleLotConsumption via properties that reach into .lot — see that model).
    """
    result = await db.execute(
        select(Holding)
        .where(Holding.id == holding_id, Holding.portfolio_id == portfolio_id)
        .options(
            selectinload(Holding.asset),
            selectinload(Holding.lots),
            selectinload(Holding.sales)
            .selectinload(Sale.lot_consumptions)
            .selectinload(SaleLotConsumption.lot),
        )
    )
    return result.scalar_one_or_none()


def compute_holding_aggregates(lots: list[Lot]) -> dict:
    """Compute derived aggregates from the lot list (Spec D03 §8).

    Skips lots where fx_rate_at_purchase is None (manual_pending) for
    base-currency calculations. Returns zero for all fields if no lots.
    """
    zero = Decimal("0")
    qty_held = zero
    total_invested_base = zero
    weighted_price_quote_num = zero  # numerator for weighted avg in quote currency
    weighted_price_base_num = zero   # numerator for weighted avg in base currency

    for lot in lots:
        remaining = lot.quantity - lot.quantity_consumed
        if remaining <= zero:
            continue
        qty_held += remaining
        weighted_price_quote_num += remaining * lot.unit_price
        if lot.fx_rate_at_purchase is not None:
            cost_base = remaining * lot.unit_price * lot.fx_rate_at_purchase
            total_invested_base += cost_base
            weighted_price_base_num += cost_base

    avg_price_quote = (weighted_price_quote_num / qty_held) if qty_held > zero else zero
    avg_price_base = (weighted_price_base_num / qty_held) if qty_held > zero else zero

    return {
        "quantity_held": qty_held,
        "total_invested_base": total_invested_base,
        "avg_purchase_price_quote": avg_price_quote,
        "avg_purchase_price_base": avg_price_base,
    }


# ── Lot CRUD ──────────────────────────────────────────────────────────────────


async def add_lot(
    db: AsyncSession,
    holding: Holding,
    *,
    purchase_date,
    quantity: Decimal,
    unit_price: Decimal,
    fx_rate_at_purchase: Decimal | None,
    fx_rate_origin: str,
    notes: str | None,
) -> Lot:
    """Add a lot to an existing holding. Caller must commit afterwards.

    Raises ValueError if quantity or unit_price is not > 0.
    """
    if quantity <= 0:
        raise ValueError("Lot quantity must be greater than zero.")
    if unit_price <= 0:
        raise ValueError("Lot unit_price must be greater than zero.")
    if fx_rate_origin != "manual_pending" and fx_rate_at_purchase is None:
        raise ValueError(
            "fx_rate_at_purchase is required unless fx_rate_origin is 'manual_pending'."
        )

    lot = Lot(
        holding_id=holding.id,
        purchase_date=purchase_date,
        quantity=quantity,
        unit_price=unit_price,
        fx_rate_at_purchase=fx_rate_at_purchase,
        fx_rate_origin=fx_rate_origin,
        notes=notes,
        quantity_consumed=Decimal("0"),
    )
    db.add(lot)
    await db.flush()
    return lot


async def edit_lot(
    db: AsyncSession,
    lot: Lot,
    *,
    purchase_date=None,
    quantity: Decimal | None = None,
    unit_price: Decimal | None = None,
    fx_rate_at_purchase: Decimal | None = None,
    fx_rate_origin: str | None = None,
    notes: str | None = None,
) -> Lot:
    """Edit an unconsumed lot. Caller must commit afterwards.

    Raises ValueError if the lot has been partially or fully consumed (Spec D03 §6.2).
    """
    if lot.quantity_consumed > 0:
        raise ValueError(
            "This lot has been consumed by one or more sales and cannot be edited. "
            "Delete the dependent sale(s) first."
        )
    if quantity is not None:
        if quantity <= 0:
            raise ValueError("Lot quantity must be greater than zero.")
        lot.quantity = quantity
    if unit_price is not None:
        if unit_price <= 0:
            raise ValueError("Lot unit_price must be greater than zero.")
        lot.unit_price = unit_price
    if purchase_date is not None:
        lot.purchase_date = purchase_date
    if fx_rate_at_purchase is not None:
        lot.fx_rate_at_purchase = fx_rate_at_purchase
    if fx_rate_origin is not None:
        lot.fx_rate_origin = fx_rate_origin
    if notes is not None:
        lot.notes = notes

    await db.flush()
    return lot


async def delete_lot(db: AsyncSession, lot: Lot) -> None:
    """Delete a lot. Caller must commit afterwards.

    Raises ValueError if the lot has been consumed by sales (Spec D03 §6.2).
    The parent holding is preserved even if this was its last lot (Spec D03 §6.3) —
    it is only removed via the explicit "delete asset" action.
    """
    if lot.quantity_consumed > 0:
        raise ValueError(
            "This lot has been consumed by one or more sales and cannot be deleted. "
            "Delete the dependent sale(s) first."
        )

    await db.delete(lot)
    await db.flush()
