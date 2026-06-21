"""Lot ORM model — Spec D03 §3.3.

A single purchase event within a Holding. Immutable in concept (historical fact)
but editable while not consumed by any sale. quantity_consumed is maintained
transactionally as sales are created/deleted (FIFO — see sale_service.py).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_FX_ORIGIN_ENUM = Enum(
    "auto", "manual", "corrected", "manual_pending",
    name="fx_rate_origin_enum",
)


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Must be > 0. Validated at the service layer.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    # Price per unit in the asset's quote_currency.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    # Null only when fx_rate_origin = 'manual_pending' (FX provider unavailable at creation).
    fx_rate_at_purchase: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_origin: Mapped[str] = mapped_column(
        _FX_ORIGIN_ENUM, nullable=False, server_default="manual"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tracks how many units have been consumed by sales (FIFO). Initially 0.
    quantity_consumed: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    holding: Mapped["Holding"] = relationship(back_populates="lots")  # type: ignore[name-defined]
    sale_consumptions: Mapped[list["SaleLotConsumption"]] = relationship(  # type: ignore[name-defined]
        back_populates="lot", cascade="all, delete-orphan"
    )

    @property
    def quantity_remaining(self) -> Decimal:
        return self.quantity - self.quantity_consumed

    def __repr__(self) -> str:
        return (
            f"<Lot id={self.id} date={self.purchase_date} "
            f"qty={self.quantity} consumed={self.quantity_consumed}>"
        )
