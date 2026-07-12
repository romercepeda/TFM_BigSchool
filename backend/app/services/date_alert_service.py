"""DateAlert business logic — Changeset C17.

Covers CRUD on DateAlert and the portfolio-wide aggregation used by the
Alerts Panel. Unlike price_level_service, there is no history table and no
crossing engine: status is a pure function of alert_date vs. today, computed
by DateAlert.status at read time (never stored).
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset
from app.db.models.date_alert import DateAlert
from app.db.models.holding import Holding


# ── Queries ──────────────────────────────────────────────────────────────────


async def get_date_alert(
    db: AsyncSession, alert_id: UUID, holding_id: UUID
) -> DateAlert | None:
    result = await db.execute(
        select(DateAlert).where(
            DateAlert.id == alert_id,
            DateAlert.holding_id == holding_id,
        )
    )
    return result.scalar_one_or_none()


async def list_date_alerts(db: AsyncSession, holding_id: UUID) -> list[DateAlert]:
    result = await db.execute(
        select(DateAlert)
        .where(DateAlert.holding_id == holding_id)
        .order_by(DateAlert.alert_date.asc())
    )
    return list(result.scalars().all())


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_date_alert(
    db: AsyncSession, holding_id: UUID, *, alert_date: date, description: str
) -> DateAlert:
    alert = DateAlert(holding_id=holding_id, alert_date=alert_date, description=description)
    db.add(alert)
    await db.flush()
    return alert


async def edit_date_alert(
    db: AsyncSession,
    alert: DateAlert,
    *,
    alert_date: date | None = None,
    description: str | None = None,
) -> DateAlert:
    """Edit a date alert. Always allowed, no touched-style lock (Changeset C17 §1)."""
    if alert_date is not None:
        alert.alert_date = alert_date
    if description is not None:
        alert.description = description
    await db.flush()
    return alert


async def mark_alert_seen(db: AsyncSession, alert: DateAlert) -> DateAlert:
    """Acknowledge a due alert. Raises ValueError if still 'pending' (nothing to acknowledge)."""
    if alert.status != "due":
        raise ValueError("Only a due alert can be marked as read.")

    alert.alert_seen_at = datetime.now(UTC)
    await db.flush()
    return alert


async def delete_date_alert(db: AsyncSession, alert: DateAlert) -> None:
    """Hard-delete a date alert. No history entry is written (Changeset C17 §1)."""
    await db.delete(alert)
    await db.flush()


# ── Portfolio-wide Alerts Panel aggregation ───────────────────────────────────


async def list_portfolio_date_alerts(
    db: AsyncSession,
    portfolio_id: UUID,
    *,
    upcoming_days: int,
) -> tuple[list[dict], list[dict], int]:
    """Aggregate due and upcoming date alerts across a portfolio (Changeset C17 §4).

    Returns (due, upcoming, unread_count) as dicts shaped for the
    PortfolioDateAlertItem schema. 'due' is sorted by alert_date descending
    (most recently due first). 'upcoming' holds alerts within upcoming_days
    of today, sorted by alert_date ascending (soonest first). 'unread_count'
    is the number of 'due' items whose alert_seen_at is null.
    """
    result = await db.execute(
        select(DateAlert, Asset.ticker, Asset.name)
        .join(Holding, Holding.id == DateAlert.holding_id)
        .join(Asset, Asset.id == Holding.asset_id)
        .where(Holding.portfolio_id == portfolio_id)
    )
    rows = result.all()
    if not rows:
        return [], [], 0

    today = datetime.now(UTC).date()
    upcoming_limit = today.toordinal() + upcoming_days

    due: list[dict] = []
    upcoming: list[dict] = []

    for alert, ticker, name in rows:
        item = {
            "id": alert.id,
            "holding_id": alert.holding_id,
            "alert_date": alert.alert_date,
            "description": alert.description,
            "status": alert.status,
            "created_at": alert.created_at,
            "updated_at": alert.updated_at,
            "alert_seen_at": alert.alert_seen_at,
            "asset_ticker": ticker,
            "asset_name": name,
        }
        if alert.alert_date <= today:
            due.append(item)
        elif alert.alert_date.toordinal() <= upcoming_limit:
            upcoming.append(item)

    due.sort(key=lambda i: i["alert_date"], reverse=True)
    upcoming.sort(key=lambda i: i["alert_date"])
    unread_count = sum(1 for i in due if i["alert_seen_at"] is None)

    return due, upcoming, unread_count
