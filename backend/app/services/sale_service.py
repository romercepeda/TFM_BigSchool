"""Sale business logic — FIFO cost-basis computation and sale CRUD.

Spec D13 §3/§4.2: FIFO is the single source of truth for cost basis. Realized-
gain fields (cost_basis_*, realized_gain_*) are computed once at sale creation
and never recomputed (D13 §4.1, §11) — sales are immutable except for `reason`
(stored in the pre-existing `notes` column — see D13 §4.1 implementation note).

compute_fifo() is a pure function (no I/O) so create_sale() and the future
preview endpoint (Changeset C20 §3) share the exact algorithm — no
client-/endpoint-side FIFO drift (D13 §5.3). This mirrors the
pure-computation/thin-DB-fetch split already used in fx_engine.py and
summary_service.py (Spec 00c testing convention).

Deleting a sale restores all consumed quantities before hard-deleting.
"""

from dataclasses import dataclass
from datetime import date as date_
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lot import Lot
from app.db.models.sale import Sale, SaleLotConsumption

_Q_MONETARY = Decimal("0.00000001")  # 8 dp, matches fx_engine's monetary precision (D04)
_ZERO = Decimal("0")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_Q_MONETARY, rounding=ROUND_HALF_EVEN)


class InsufficientUnitsError(ValueError):
    """Raised when a sale requests more units than the holding has available.

    Subclasses ValueError so the existing `except ValueError` -> HTTP 400
    handling in the API layer keeps working unchanged; callers that need to
    tell this apart from other validation errors (e.g. a future preview
    endpoint that reports it as a soft `insufficient_units: true` rather than
    an HTTP error) can catch it specifically.
    """

    def __init__(self, units_available: Decimal, units_requested: Decimal):
        self.units_available = units_available
        self.units_requested = units_requested
        super().__init__(
            f"Insufficient position: {units_available} units available, "
            f"{units_requested} requested."
        )


# ── Pure FIFO computation (Spec D13 §3, §4.2 — no I/O, no DB) ────────────────


@dataclass(frozen=True)
class LotConsumption:
    """One lot's contribution to a sale's FIFO consumption."""
    lot_id: UUID
    purchase_date: date_
    unit_price: Decimal
    units_consumed: Decimal
    cost_contribution: Decimal  # units_consumed * unit_price, rounded


@dataclass(frozen=True)
class FifoResult:
    consumptions: tuple[LotConsumption, ...]
    units_available: Decimal
    insufficient: bool
    cost_basis_quote: Decimal
    # None if any consumed lot lacks fx_rate_at_purchase (manual_pending) — the
    # quote-currency figures are still fully valid in that case.
    cost_basis_base: Decimal | None


def compute_fifo(lots: list[Lot], quantity: Decimal) -> FifoResult:
    """Compute FIFO lot consumption for `quantity` units, oldest lot first.

    `lots` must already be ordered by purchase_date ASC, created_at ASC
    (Spec D03 §7.2 / D13 §4.2). Pure: does not mutate `lots` or touch the
    database — callers apply the result (or reject it) themselves.
    """
    units_available = sum((lot.quantity - lot.quantity_consumed for lot in lots), _ZERO)
    if units_available < quantity:
        return FifoResult(
            consumptions=(), units_available=units_available, insufficient=True,
            cost_basis_quote=_ZERO, cost_basis_base=None,
        )

    consumptions: list[LotConsumption] = []
    remaining = quantity
    cost_basis_quote_exact = _ZERO
    cost_basis_base_exact: Decimal | None = _ZERO

    for lot in lots:
        if remaining <= _ZERO:
            break
        available = lot.quantity - lot.quantity_consumed
        if available <= _ZERO:
            continue

        units = min(available, remaining)
        remaining -= units
        cost_basis_quote_exact += units * lot.unit_price
        if cost_basis_base_exact is not None:
            if lot.fx_rate_at_purchase is None:
                cost_basis_base_exact = None
            else:
                cost_basis_base_exact += units * lot.unit_price * lot.fx_rate_at_purchase

        consumptions.append(LotConsumption(
            lot_id=lot.id,
            purchase_date=lot.purchase_date,
            unit_price=lot.unit_price,
            units_consumed=units,
            cost_contribution=_round(units * lot.unit_price),
        ))

    return FifoResult(
        consumptions=tuple(consumptions),
        units_available=units_available,
        insufficient=False,
        cost_basis_quote=_round(cost_basis_quote_exact),
        cost_basis_base=_round(cost_basis_base_exact) if cost_basis_base_exact is not None else None,
    )


# ── Thin DB-fetching layer ────────────────────────────────────────────────────


async def _fetch_active_lots(db: AsyncSession, holding_id: UUID) -> list[Lot]:
    result = await db.execute(
        select(Lot)
        .where(
            Lot.holding_id == holding_id,
            Lot.quantity_consumed < Lot.quantity,
        )
        .order_by(Lot.purchase_date.asc(), Lot.created_at.asc())
    )
    return list(result.scalars().all())


async def _revert_consumptions(db: AsyncSession, sale_id: UUID) -> None:
    """Remove all SaleLotConsumption rows for a sale and restore each lot's quantity_consumed."""
    result = await db.execute(
        select(SaleLotConsumption).where(SaleLotConsumption.sale_id == sale_id)
    )
    consumptions = list(result.scalars().all())
    for c in consumptions:
        lot_result = await db.execute(select(Lot).where(Lot.id == c.lot_id))
        lot = lot_result.scalar_one()
        lot.quantity_consumed = lot.quantity_consumed - c.quantity_consumed
        await db.delete(c)
    await db.flush()


# ── Sale CRUD (Spec D13 §7, §11) ──────────────────────────────────────────────


async def create_sale(
    db: AsyncSession,
    holding_id: UUID,
    *,
    sale_date,
    quantity: Decimal,
    unit_price: Decimal,
    fx_rate_at_sale: Decimal | None,
    fx_rate_origin: str,
    notes: str | None,
) -> Sale:
    """Register a sale: run FIFO consumption and persist the immutable
    realized-gain fields alongside it (D13 §4.1, §7.2). Caller must commit.

    Raises ValueError if quantity/price is invalid, InsufficientUnitsError if
    the position can't cover the requested quantity — either way, nothing is
    written.
    """
    if quantity <= 0:
        raise ValueError("Sale quantity must be greater than zero.")
    if unit_price <= 0:
        raise ValueError("Sale unit_price must be greater than zero.")
    if fx_rate_origin != "manual_pending" and fx_rate_at_sale is None:
        raise ValueError(
            "fx_rate_at_sale is required unless fx_rate_origin is 'manual_pending'."
        )

    lots = await _fetch_active_lots(db, holding_id)
    fifo = compute_fifo(lots, quantity)
    if fifo.insufficient:
        raise InsufficientUnitsError(fifo.units_available, quantity)

    proceeds_quote = _round(quantity * unit_price)
    realized_gain_quote = _round(proceeds_quote - fifo.cost_basis_quote)

    cost_basis_base = fifo.cost_basis_base
    realized_gain_base: Decimal | None = None
    if cost_basis_base is not None and fx_rate_at_sale is not None:
        proceeds_base = _round(quantity * unit_price * fx_rate_at_sale)
        realized_gain_base = _round(proceeds_base - cost_basis_base)
    else:
        cost_basis_base = None  # keep the two base-currency fields in lockstep

    sale = Sale(
        holding_id=holding_id,
        sale_date=sale_date,
        quantity=quantity,
        unit_price=unit_price,
        fx_rate_at_sale=fx_rate_at_sale,
        fx_rate_origin=fx_rate_origin,
        notes=notes,
        cost_basis_quote=fifo.cost_basis_quote,
        cost_basis_base=cost_basis_base,
        realized_gain_quote=realized_gain_quote,
        realized_gain_base=realized_gain_base,
    )
    db.add(sale)
    await db.flush()  # assigns sale.id needed for the SaleLotConsumption rows

    lots_by_id = {lot.id: lot for lot in lots}
    for c in fifo.consumptions:
        db.add(SaleLotConsumption(
            sale_id=sale.id,
            lot_id=c.lot_id,
            quantity_consumed=c.units_consumed,
        ))
        lots_by_id[c.lot_id].quantity_consumed += c.units_consumed

    await db.flush()
    return sale


async def update_reason(db: AsyncSession, sale: Sale, notes: str | None) -> Sale:
    """Update only a sale's reason (D13 §11) — every other field is locked
    once the sale is created. `updated_at` still bumps via the model's
    onupdate; no other side effect (no cache invalidation — D13 §8.1: a
    reason edit has no financial impact). Caller must commit.
    """
    sale.notes = notes
    await db.flush()
    return sale


async def delete_sale(db: AsyncSession, sale: Sale) -> None:
    """Delete a sale and restore all consumed lot quantities. Caller must commit."""
    await _revert_consumptions(db, sale.id)
    await db.delete(sale)
    await db.flush()


async def get_sale(db: AsyncSession, sale_id: UUID, holding_id: UUID) -> Sale | None:
    result = await db.execute(
        select(Sale).where(Sale.id == sale_id, Sale.holding_id == holding_id)
    )
    return result.scalar_one_or_none()
