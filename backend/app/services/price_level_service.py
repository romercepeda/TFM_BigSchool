"""Price level business logic — Spec D06.

Covers:
  - CRUD on PriceLevel with atomic history writes (Spec D06 §4.1)
  - Alert crossing detection (pure function — Spec D06 §5.2)
  - Alert application: touch levels that crossed and write 'touched' history

Key invariants enforced here:
  - Every PriceLevel state change writes a history entry in the same flush.
  - Touched levels can only have their note edited (Spec D06 §3.2).
  - Fully consumed direction-crossing rule: buy touches on downward crossing,
    sell touches on upward crossing (Spec D06 §5.2 and §5.3).
"""

from datetime import UTC, datetime, date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.holding import Holding
from app.db.models.price_level import PriceLevel, PriceLevelHistoryEntry


# ── Internal helper ──────────────────────────────────────────────────────────


def _history(
    level: PriceLevel,
    event_type: str,
    asset_price_at_event: Decimal | None,
) -> PriceLevelHistoryEntry:
    """Build an immutable history entry snapshotting the level's current state."""
    return PriceLevelHistoryEntry(
        holding_id=level.holding_id,
        originating_level_id=level.id,
        event_type=event_type,
        event_at=datetime.now(UTC),
        direction=level.direction,
        target_price=level.target_price,
        note=level.note,
        asset_price_at_event=asset_price_at_event,
    )


# ── Queries ──────────────────────────────────────────────────────────────────


async def get_price_level(
    db: AsyncSession, level_id: UUID, holding_id: UUID
) -> PriceLevel | None:
    result = await db.execute(
        select(PriceLevel).where(
            PriceLevel.id == level_id,
            PriceLevel.holding_id == holding_id,
        )
    )
    return result.scalar_one_or_none()


async def list_price_levels(
    db: AsyncSession, holding_id: UUID
) -> list[PriceLevel]:
    result = await db.execute(
        select(PriceLevel)
        .where(PriceLevel.holding_id == holding_id)
        .order_by(PriceLevel.created_at.asc())
    )
    return list(result.scalars().all())


async def list_price_level_history(
    db: AsyncSession, holding_id: UUID
) -> list[PriceLevelHistoryEntry]:
    result = await db.execute(
        select(PriceLevelHistoryEntry)
        .where(PriceLevelHistoryEntry.holding_id == holding_id)
        .order_by(PriceLevelHistoryEntry.event_at.desc())
    )
    return list(result.scalars().all())


# ── CRUD with atomic history writes ──────────────────────────────────────────


async def create_price_levels(
    db: AsyncSession,
    holding_id: UUID,
    levels: list[dict],
    *,
    asset_price_at_event: Decimal | None = None,
) -> list[PriceLevel]:
    """Create one or more price levels in a single atomic operation (Spec D06 §8).

    Each dict must have: direction (str), target_price (Decimal), note (str|None).
    Raises ValueError if the list is empty or target_price is not > 0.
    """
    if not levels:
        raise ValueError("At least one price level must be provided.")

    created: list[PriceLevel] = []
    for item in levels:
        target = item["target_price"]
        if target <= Decimal("0"):
            raise ValueError("target_price must be greater than zero.")

        level = PriceLevel(
            holding_id=holding_id,
            direction=item["direction"],
            target_price=target,
            note=item.get("note"),
            status="armed",
        )
        db.add(level)
        await db.flush()  # populate level.id before building history entry

        db.add(_history(level, "created", asset_price_at_event))
        created.append(level)

    await db.flush()
    return created


async def edit_price_level(
    db: AsyncSession,
    level: PriceLevel,
    *,
    direction: str | None = None,
    target_price: Decimal | None = None,
    note: str | None = None,
    asset_price_at_event: Decimal | None = None,
) -> PriceLevel:
    """Edit a price level and write an 'edited' history entry (Spec D06 §3.2).

    Raises ValueError if the level is 'touched' and a field other than note
    is being changed (Spec D06 §3.2).
    """
    if level.status == "touched":
        if direction is not None or target_price is not None:
            raise ValueError(
                "A touched level can only have its note edited. "
                "To change direction or target price, delete this level and create a new one."
            )

    changed = False
    if direction is not None:
        level.direction = direction
        changed = True
    if target_price is not None:
        if target_price <= Decimal("0"):
            raise ValueError("target_price must be greater than zero.")
        level.target_price = target_price
        changed = True
    if note is not None:
        level.note = note
        changed = True

    if not changed:
        return level

    db.add(_history(level, "edited", asset_price_at_event))
    await db.flush()
    return level


async def delete_price_level(
    db: AsyncSession,
    level: PriceLevel,
    *,
    asset_price_at_event: Decimal | None = None,
) -> None:
    """Write a 'removed' history entry then hard-delete the level (Spec D06 §3.3).

    The history entry survives; the PriceLevel row is gone.
    """
    db.add(_history(level, "removed", asset_price_at_event))
    await db.flush()
    await db.delete(level)
    await db.flush()


# ── Alert engine ──────────────────────────────────────────────────────────────


def find_crossings(
    levels: list[PriceLevel],
    previous_close: Decimal,
    current_close: Decimal,
) -> list[PriceLevel]:
    """Pure function: return armed levels that should be touched (Spec D06 §5.2).

    Buy level  → touched when previous_close > target_price AND current_close <= target_price.
    Sell level → touched when previous_close < target_price AND current_close >= target_price.

    Already-touched levels are never re-triggered (Spec D06 §5.1).
    """
    result = []
    for level in levels:
        if level.status != "armed":
            continue
        tp = level.target_price
        if level.direction == "buy" and previous_close > tp and current_close <= tp:
            result.append(level)
        elif level.direction == "sell" and previous_close < tp and current_close >= tp:
            result.append(level)
    return result


async def apply_crossings(
    db: AsyncSession,
    holding_id: UUID,
    *,
    previous_close: Decimal,
    current_close: Decimal,
    close_date: date,
) -> list[PriceLevel]:
    """Evaluate all armed levels for a holding and touch any that crossed.

    Loads armed levels, calls find_crossings (pure), then persists touches
    and writes 'touched' history entries — all in the caller's transaction.

    Returns the list of levels that were touched this run (may be empty).
    """
    armed = await db.execute(
        select(PriceLevel).where(
            PriceLevel.holding_id == holding_id,
            PriceLevel.status == "armed",
        )
    )
    levels = list(armed.scalars().all())
    crossed = find_crossings(levels, previous_close, current_close)

    touched_at = datetime.now(UTC)
    for level in crossed:
        level.status = "touched"
        level.touched_at = touched_at
        level.touched_at_close_price = current_close
        level.touched_at_close_date = close_date
        db.add(_history(level, "touched", current_close))

    if crossed:
        await db.flush()

    return crossed


# ── Portfolio hard-delete helper ──────────────────────────────────────────────


async def delete_history_for_portfolio(db: AsyncSession, portfolio_id: UUID) -> None:
    """Delete all PriceLevelHistoryEntry rows for all holdings in a portfolio.

    Called by portfolio_service.delete_portfolio BEFORE the portfolio ORM
    delete, because history entries have no FK cascade to holdings (Spec D06 §11).
    """
    from app.db.models.holding import Holding  # avoid circular at module level

    holding_ids_subq = select(Holding.id).where(Holding.portfolio_id == portfolio_id)
    await db.execute(
        delete(PriceLevelHistoryEntry).where(
            PriceLevelHistoryEntry.holding_id.in_(holding_ids_subq)
        )
    )
