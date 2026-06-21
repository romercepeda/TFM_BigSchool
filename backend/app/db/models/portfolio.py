"""Portfolio ORM model — Spec D02 (Portfolio Management).

Maps to the `portfolios` table. A Portfolio belongs to one User and
contains Holdings (assets). Its base_currency is immutable after creation
(see Spec D02 §5 for the rationale).

Lifecycle: active → archived (soft delete) → permanently deleted (hard delete).
Archived portfolios are hidden from the UI but all data is preserved.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Supported base currencies in v1 (Spec D02 §2).
_CURRENCY_ENUM = Enum(
    "EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD",
    name="portfolio_currency_enum",
)

_STATUS_ENUM = Enum(
    "active", "archived",
    name="portfolio_status_enum",
)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Immutable after creation — changing it would invalidate all historical KPIs.
    base_currency: Mapped[str] = mapped_column(_CURRENCY_ENUM, nullable=False)
    status: Mapped[str] = mapped_column(
        _STATUS_ENUM, nullable=False, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    # Set when archived; cleared (null) when restored. See Spec D02 §6 and §7.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="portfolios")  # type: ignore[name-defined]
    holdings: Mapped[list["Holding"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<Portfolio id={self.id} name={self.name!r} "
            f"currency={self.base_currency!r} status={self.status!r}>"
        )
