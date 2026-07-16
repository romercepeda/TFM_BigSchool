"""Sale and SaleLotConsumption ORM models — Spec D03 §3.4/§3.5, extended by Spec D13 §4.1.

Sale: a single sale event within a Holding. The four realized-gain columns
(cost_basis_*, realized_gain_*) are populated once at creation by SaleService
and never recomputed (D13 §4.1, §11) — `notes` doubles as D13's "reason" field.
SaleLotConsumption: the FIFO junction — records exactly which lots each sale consumed
and how many units were taken from each. Source of truth for realized-gain accounting.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.lot import _FX_ORIGIN_ENUM


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Must be > 0. Validated at the service layer.
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    # Price per unit at sale, in the asset's quote_currency.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    # Null only when fx_rate_origin = 'manual_pending'.
    fx_rate_at_sale: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_origin: Mapped[str] = mapped_column(
        _FX_ORIGIN_ENUM, nullable=False, server_default="manual"
    )
    # Doubles as D13 §4.1's "reason" field — max 500 chars enforced at the API layer.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Realized-gain fields (Spec D13 §4.1). Populated once at sale creation by
    # SaleService and never recomputed — nullable only to accommodate sales
    # created before D13 (backfilled by migration; NULL if backfill was impossible).
    cost_basis_quote: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_basis_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    realized_gain_quote: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    realized_gain_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    holding: Mapped["Holding"] = relationship(back_populates="sales")  # type: ignore[name-defined]
    lot_consumptions: Mapped[list["SaleLotConsumption"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Sale id={self.id} date={self.sale_date} qty={self.quantity}>"


class SaleLotConsumption(Base):
    """FIFO junction — which lots a sale consumed, and how many units from each."""

    __tablename__ = "sale_lot_consumptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sale_id: Mapped[UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lot_id: Mapped[UUID] = mapped_column(
        ForeignKey("lots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Exact units taken from this lot by this sale.
    quantity_consumed: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="lot_consumptions")
    lot: Mapped["Lot"] = relationship(back_populates="sale_consumptions")

    # D13 §6.1's FIFO breakdown ("which lots were consumed, at what cost")
    # needs these, but they live on the consumed Lot, not on this junction
    # row. Exposed as properties so SaleLotConsumptionResponse.model_validate
    # (from_attributes) picks them up transparently everywhere a Sale is
    # serialized — the only requirement is that .lot is eager-loaded
    # (a lazy load here would raise in an async context).
    @property
    def purchase_date(self) -> date:
        return self.lot.purchase_date

    @property
    def unit_price(self) -> Decimal:
        return self.lot.unit_price

    @property
    def cost_contribution(self) -> Decimal:
        return self.quantity_consumed * self.lot.unit_price

    def __repr__(self) -> str:
        return (
            f"<SaleLotConsumption sale={self.sale_id} lot={self.lot_id} "
            f"qty={self.quantity_consumed}>"
        )
