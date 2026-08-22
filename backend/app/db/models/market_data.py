"""AssetPriceHistory and FxRateHistory ORM models — Spec D09.

Both tables are append-only across trading days: the daily job inserts with
ON CONFLICT DO NOTHING, so a past day's close is never overwritten. The one
exception is AssetPriceHistory's own day: a manual "refresh price" action
(MarketDataService.refresh_and_store_current_price) is allowed to update
*today's* row, since it represents a newer, explicit observation than
whatever the daily job or a previous refresh wrote for today.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# "eodhd" added by Spec D12 / Changeset C04 Step 7 — the cascade can now
# persist price rows sourced from EODHD.
_MARKET_PROVIDER_ENUM = Enum("twelve_data", "finnhub", "eodhd", name="market_provider_enum")


class AssetPriceHistory(Base):
    __tablename__ = "asset_price_history"
    __table_args__ = (
        UniqueConstraint("asset_id", "as_of_date", name="uq_asset_price_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    provider: Mapped[str] = mapped_column(_MARKET_PROVIDER_ENUM, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AssetPriceHistory asset_id={self.asset_id} "
            f"date={self.as_of_date} price={self.close_price}>"
        )


class FxRateHistory(Base):
    __tablename__ = "fx_rate_history"
    __table_args__ = (
        UniqueConstraint(
            "quote_currency", "base_currency", "as_of_date", name="uq_fx_pair_date"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Convention: how many units of base_currency one unit of quote_currency buys (D04 §3.1).
    rate: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<FxRateHistory {self.quote_currency}/{self.base_currency} "
            f"date={self.as_of_date} rate={self.rate}>"
        )
