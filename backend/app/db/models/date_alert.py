"""DateAlert ORM model — Changeset C17.

A lightweight, per-holding "remind me on this date" alert. Modeled after
PriceLevel but deliberately simpler: no immutable history table and no
crossing engine, because a date alert carries no analytical record worth
preserving and its status is a pure function of alert_date vs. today
(computed at read time, never stored — see date_alert_service.py).
"""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DateAlert(Base):
    """A date + short description attached to a holding (Changeset C17 §2)."""
    __tablename__ = "date_alerts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    # Null = unread alert. Only meaningful once the alert is 'due'
    # (alert_date <= today) — mirrors PriceLevel.alert_seen_at (Changeset C12).
    alert_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    holding: Mapped["Holding"] = relationship(back_populates="date_alerts")  # type: ignore[name-defined]

    @property
    def status(self) -> str:
        """Derived, never stored (Changeset C17 §3): 'due' once alert_date has arrived."""
        return "due" if self.alert_date <= datetime.now(UTC).date() else "pending"

    def __repr__(self) -> str:
        return f"<DateAlert id={self.id} date={self.alert_date} desc={self.description!r}>"
