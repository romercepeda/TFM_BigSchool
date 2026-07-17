"""AssetDividendSchedule and DividendPayment ORM models — Spec D15 §3.

AssetDividendSchedule: the declared dividend policy of an Asset (shared
reference data, one row per asset, edited in place — no history table, same
simplicity choice already made for DateAlert per Changeset C17).

DividendPayment: a holding-scoped record of an actual dividend cash payment
received by the user. Immutable except `notes`, mirrors Sale (Spec D13).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.lot import _FX_ORIGIN_ENUM

_DIVIDEND_FREQUENCY_ENUM = Enum(
    "monthly", "quarterly", "semiannual", "annual", "irregular",
    name="dividend_frequency_enum",
)

_DIVIDEND_SCHEDULE_ORIGIN_ENUM = Enum(
    "manual", "auto",
    name="dividend_schedule_origin_enum",
)

_DIVIDEND_AMOUNT_TYPE_ENUM = Enum(
    "nominal", "percentage",
    name="dividend_amount_type_enum",
)


class AssetDividendSchedule(Base):
    __tablename__ = "asset_dividend_schedules"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    frequency: Mapped[str] = mapped_column(_DIVIDEND_FREQUENCY_ENUM, nullable=False)
    # 'nominal': amount_per_payment is a currency amount per share, in
    # quote_currency. 'percentage': amount_per_payment is a percentage value
    # (e.g. 2.5 for "2.5%") of the current share price at computation time —
    # some companies announce dividends this way instead of a fixed amount.
    # Added after v1 shipped (user feedback: the declared figure is a
    # reference the user copies from the company's announcement verbatim,
    # in whichever unit that announcement used).
    amount_type: Mapped[str] = mapped_column(
        _DIVIDEND_AMOUNT_TYPE_ENUM, nullable=False, server_default="nominal"
    )
    # Declared amount per payment. In quote_currency if amount_type='nominal';
    # a plain percentage number (not a fraction) if amount_type='percentage'.
    amount_per_payment: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    next_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin: Mapped[str] = mapped_column(
        _DIVIDEND_SCHEDULE_ORIGIN_ENUM, nullable=False, server_default="manual"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    asset: Mapped["Asset"] = relationship(back_populates="dividend_schedule")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<AssetDividendSchedule asset_id={self.asset_id} "
            f"freq={self.frequency} amount={self.amount_per_payment}>"
        )


class DividendPayment(Base):
    __tablename__ = "dividend_payments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Total gross amount received, in the asset's quote_currency (not per-share).
    gross_amount_quote: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    # Null only when fx_rate_origin = 'manual_pending' (FX provider unavailable at creation).
    fx_rate_at_payment: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_origin: Mapped[str] = mapped_column(
        _FX_ORIGIN_ENUM, nullable=False, server_default="manual"
    )
    # gross_amount_quote * fx_rate_at_payment, computed once at creation and
    # never recomputed (D15 §3.2) — null only if FX was unresolved at creation.
    gross_amount_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    holding: Mapped["Holding"] = relationship(back_populates="dividend_payments")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<DividendPayment id={self.id} holding_id={self.holding_id} "
            f"date={self.payment_date} gross={self.gross_amount_quote}>"
        )
