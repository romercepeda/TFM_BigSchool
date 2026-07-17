"""Holding ORM model — Spec D03 §3.2.

The link between a Portfolio and an Asset. One holding per (portfolio, asset) pair.
Auto-created when the first lot for a portfolio-asset pair is added.
Auto-deleted when its last lot is removed and no sales remain (handled in lot_service).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "asset_id", name="uq_holding_portfolio_asset"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    portfolio_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")  # type: ignore[name-defined]
    asset: Mapped["Asset"] = relationship(back_populates="holdings")  # type: ignore[name-defined]
    lots: Mapped[list["Lot"]] = relationship(back_populates="holding", cascade="all, delete-orphan")  # type: ignore[name-defined]
    sales: Mapped[list["Sale"]] = relationship(back_populates="holding", cascade="all, delete-orphan")  # type: ignore[name-defined]
    price_levels: Mapped[list["PriceLevel"]] = relationship(back_populates="holding", cascade="all, delete-orphan")  # type: ignore[name-defined]
    date_alerts: Mapped[list["DateAlert"]] = relationship(back_populates="holding", cascade="all, delete-orphan")  # type: ignore[name-defined]
    dividend_payments: Mapped[list["DividendPayment"]] = relationship(back_populates="holding", cascade="all, delete-orphan")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Holding id={self.id} portfolio_id={self.portfolio_id} asset_id={self.asset_id}>"
