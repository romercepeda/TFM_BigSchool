"""Sale business logic — register, edit, delete with FIFO lot consumption.

FIFO algorithm (Spec D03 §7.2):
  1. List lots with remaining quantity, ordered by purchase_date ASC, created_at ASC.
  2. Walk the list, consuming from each lot until the sale quantity is satisfied.
  3. Create SaleLotConsumption rows and update lot.quantity_consumed in the same flush.
  4. Reject the entire sale if total available < requested quantity.

Editing a sale's quantity triggers a full FIFO recomputation:
  remove old consumptions → restore lot.quantity_consumed → re-run FIFO.

Deleting a sale restores all consumed quantities before hard-deleting.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lot import Lot
from app.db.models.sale import Sale, SaleLotConsumption


# ── FIFO helpers ──────────────────────────────────────────────────────────────


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


async def _apply_fifo(
    db: AsyncSession, sale: Sale, holding_id: UUID, quantity: Decimal
) -> None:
    """Run FIFO consumption for `quantity` units under `holding_id`.

    Creates SaleLotConsumption rows and updates lot.quantity_consumed.
    Raises ValueError if the holding has insufficient available position.
    """
    result = await db.execute(
        select(Lot)
        .where(
            Lot.holding_id == holding_id,
            Lot.quantity_consumed < Lot.quantity,
        )
        .order_by(Lot.purchase_date.asc(), Lot.created_at.asc())
    )
    lots = list(result.scalars().all())

    available = sum(lot.quantity - lot.quantity_consumed for lot in lots)
    if available < quantity:
        raise ValueError(
            f"Insufficient position: {available} units available, {quantity} requested."
        )

    remaining = quantity
    for lot in lots:
        if remaining <= 0:
            break
        lot_available = lot.quantity - lot.quantity_consumed
        consumed = min(lot_available, remaining)
        lot.quantity_consumed = lot.quantity_consumed + consumed
        remaining -= consumed
        db.add(SaleLotConsumption(
            sale_id=sale.id,
            lot_id=lot.id,
            quantity_consumed=consumed,
        ))

    await db.flush()


# ── Sale CRUD ─────────────────────────────────────────────────────────────────


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
    """Register a sale and apply FIFO lot consumption. Caller must commit afterwards.

    Raises ValueError if quantity/price is invalid or the position is insufficient.
    """
    if quantity <= 0:
        raise ValueError("Sale quantity must be greater than zero.")
    if unit_price <= 0:
        raise ValueError("Sale unit_price must be greater than zero.")
    if fx_rate_origin != "manual_pending" and fx_rate_at_sale is None:
        raise ValueError(
            "fx_rate_at_sale is required unless fx_rate_origin is 'manual_pending'."
        )

    sale = Sale(
        holding_id=holding_id,
        sale_date=sale_date,
        quantity=quantity,
        unit_price=unit_price,
        fx_rate_at_sale=fx_rate_at_sale,
        fx_rate_origin=fx_rate_origin,
        notes=notes,
    )
    db.add(sale)
    await db.flush()  # assigns sale.id needed for FIFO rows

    await _apply_fifo(db, sale, holding_id, quantity)
    return sale


async def edit_sale(
    db: AsyncSession,
    sale: Sale,
    *,
    sale_date=None,
    quantity: Decimal | None = None,
    unit_price: Decimal | None = None,
    fx_rate_at_sale: Decimal | None = None,
    fx_rate_origin: str | None = None,
    notes: str | None = None,
) -> Sale:
    """Edit a sale. If quantity changes, FIFO is fully recomputed. Caller must commit.

    Raises ValueError if the new quantity exceeds available position.
    """
    quantity_changed = quantity is not None and quantity != sale.quantity

    if quantity is not None and quantity <= 0:
        raise ValueError("Sale quantity must be greater than zero.")
    if unit_price is not None and unit_price <= 0:
        raise ValueError("Sale unit_price must be greater than zero.")

    if quantity_changed:
        # Revert old consumption, then re-apply with new quantity.
        await _revert_consumptions(db, sale.id)
        sale.quantity = quantity
        await db.flush()
        await _apply_fifo(db, sale, sale.holding_id, quantity)

    if sale_date is not None:
        sale.sale_date = sale_date
    if unit_price is not None:
        sale.unit_price = unit_price
    if fx_rate_at_sale is not None:
        sale.fx_rate_at_sale = fx_rate_at_sale
    if fx_rate_origin is not None:
        sale.fx_rate_origin = fx_rate_origin
    if notes is not None:
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
