"""PriceLevel and PriceLevelHistoryEntry ORM models — Spec D06.

Two-table design (Spec D06 §2):
  - PriceLevel: live, editable, hard-deletable. Fed to the alert engine.
  - PriceLevelHistoryEntry: immutable, append-only. The user's analysis record.

Every state change on a PriceLevel writes a history entry in the same
transaction (Spec D06 §4.1). This is what guarantees the user's past thinking
is never lost even when active levels are deleted.

Cascade rules (Spec D06 §11):
  - Holding deleted → PriceLevel rows deleted (via FK CASCADE), history entries PRESERVED.
  - Portfolio permanently deleted → both deleted (explicit service-layer cleanup in
    portfolio_service.delete_portfolio, because history entries have no FK to holdings).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_DIRECTION_ENUM = Enum("buy", "sell", name="price_level_direction_enum")
_STATUS_ENUM = Enum("armed", "touched", name="price_level_status_enum")
_EVENT_TYPE_ENUM = Enum(
    "created", "edited", "touched", "removed",
    name="price_level_event_type_enum",
)


class PriceLevel(Base):
    """An active price level (buy or sell target) attached to a holding.

    Editable while armed. Hard-deleted by the user (which writes a 'removed'
    history entry first). Alert engine marks it as 'touched' when the daily
    close crosses the target (Spec D06 §5).
    """
    __tablename__ = "price_levels"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(_DIRECTION_ENUM, nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(_STATUS_ENUM, nullable=False, server_default="armed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    # Populated by the alert engine when status transitions to 'touched'.
    touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    touched_at_close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    touched_at_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Null = unread alert. Set when the user marks a touched level's alert as
    # read (Changeset C12). Meaningless while status = armed.
    alert_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    holding: Mapped["Holding"] = relationship(back_populates="price_levels")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<PriceLevel id={self.id} dir={self.direction} "
            f"target={self.target_price} status={self.status}>"
        )


class PriceLevelHistoryEntry(Base):
    """Immutable record of every event in the lifecycle of a PriceLevel.

    holding_id is stored as a plain UUID (no FK constraint) so that history
    entries survive holding deletion — Spec D06 §11 explicitly requires this.
    Portfolio hard-delete must explicitly remove these rows in the service layer.

    originating_level_id is also not a FK (level may no longer exist — §4).
    """
    __tablename__ = "price_level_history_entries"
    __table_args__ = (
        Index("ix_plhe_holding_id", "holding_id"),
        Index("ix_plhe_originating_level_id", "originating_level_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Plain UUID — no FK constraint (history survives holding deletion, Spec D06 §11).
    holding_id: Mapped[UUID] = mapped_column(nullable=False)
    # Also plain UUID — the originating PriceLevel may have been deleted.
    originating_level_id: Mapped[UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(_EVENT_TYPE_ENUM, nullable=False)
    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Snapshotted values at the time of the event.
    direction: Mapped[str] = mapped_column(_DIRECTION_ENUM, nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The asset's quote-currency price at the time of the event (when available).
    asset_price_at_event: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<PriceLevelHistoryEntry id={self.id} event={self.event_type} "
            f"level={self.originating_level_id}>"
        )
