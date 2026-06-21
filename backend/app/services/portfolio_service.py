"""Portfolio business logic — create, list, rename, archive, restore, delete.

Sits between the API routers (app/api/) and the ORM model (app/db/models/portfolio.py).
All business rules from Spec D02 live here; routers stay thin.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.db.models.portfolio import Portfolio


async def get_portfolio_by_id(
    db: AsyncSession, portfolio_id: UUID, user_id: UUID
) -> Portfolio | None:
    """Return the portfolio if it belongs to user_id, else None."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _count_active(db: AsyncSession, user_id: UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.user_id == user_id, Portfolio.status == "active")
    )
    return result.scalar_one()


async def create_portfolio(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    base_currency: str,
) -> Portfolio:
    """Persist a new active portfolio. Caller must commit afterwards.

    Raises ValueError if the name exceeds the configured max length or the
    per-user active-portfolio limit (Spec D02 §3 and §9) would be exceeded.
    """
    config = get_config()
    if len(name) > config.portfolios.name_max_length:
        raise ValueError(
            f"Portfolio name must not exceed {config.portfolios.name_max_length} characters."
        )
    active_count = await _count_active(db, user_id)
    if active_count >= config.portfolios.max_active_per_user:
        raise ValueError(
            f"You have reached the limit of {config.portfolios.max_active_per_user} active "
            "portfolios. Archive an existing portfolio to create a new one."
        )
    portfolio = Portfolio(user_id=user_id, name=name, base_currency=base_currency)
    db.add(portfolio)
    await db.flush()
    return portfolio


async def list_portfolios(
    db: AsyncSession,
    user_id: UUID,
    *,
    include_archived: bool = False,
) -> list[Portfolio]:
    """Return portfolios for user_id, ordered by creation date ascending."""
    stmt = select(Portfolio).where(Portfolio.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(Portfolio.status == "active")
    stmt = stmt.order_by(Portfolio.created_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def rename_portfolio(
    db: AsyncSession, portfolio: Portfolio, *, name: str
) -> Portfolio:
    """Rename an active portfolio. Caller must commit afterwards.

    Raises ValueError if the portfolio is archived or the name exceeds the limit.
    """
    config = get_config()
    if len(name) > config.portfolios.name_max_length:
        raise ValueError(
            f"Portfolio name must not exceed {config.portfolios.name_max_length} characters."
        )
    if portfolio.status != "active":
        raise ValueError("Only active portfolios can be renamed. Restore it first.")
    portfolio.name = name
    await db.flush()
    return portfolio


async def archive_portfolio(db: AsyncSession, portfolio: Portfolio) -> Portfolio:
    """Soft-delete an active portfolio. Caller must commit afterwards.

    Raises ValueError if the portfolio is already archived.
    """
    if portfolio.status != "active":
        raise ValueError("Only active portfolios can be archived.")
    portfolio.status = "archived"
    portfolio.archived_at = datetime.now(UTC)
    await db.flush()
    return portfolio


async def restore_portfolio(
    db: AsyncSession, portfolio: Portfolio, user_id: UUID
) -> Portfolio:
    """Restore an archived portfolio to active. Caller must commit afterwards.

    Raises ValueError if the portfolio is not archived or the active limit would
    be exceeded (Spec D02 §7).
    """
    if portfolio.status != "archived":
        raise ValueError("Only archived portfolios can be restored.")
    config = get_config()
    active_count = await _count_active(db, user_id)
    if active_count >= config.portfolios.max_active_per_user:
        raise ValueError(
            f"You have reached the limit of {config.portfolios.max_active_per_user} active "
            "portfolios. Archive another portfolio before restoring this one."
        )
    portfolio.status = "active"
    portfolio.archived_at = None
    await db.flush()
    return portfolio


async def delete_portfolio(db: AsyncSession, portfolio: Portfolio) -> None:
    """Permanently delete an archived portfolio and all its data. Caller must commit.

    Raises ValueError if the portfolio is not archived (Spec D02 §8 — must archive first).
    Cascading deletes are handled by the FK constraints on child tables.
    """
    if portfolio.status != "archived":
        raise ValueError(
            "Only archived portfolios can be permanently deleted. Archive it first."
        )
    await db.delete(portfolio)
    await db.flush()
