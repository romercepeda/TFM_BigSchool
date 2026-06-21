"""Asset ORM model — Spec D03 §3.1.

Shared reference data: one row per ticker across all users and portfolios.
Created on-demand when any user first adds that asset to any portfolio.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_ASSET_TYPE_ENUM = Enum(
    "stock", "etf", "fund", "crypto",
    name="asset_type_enum",
)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(_ASSET_TYPE_ENUM, nullable=False)
    # Currency the asset is quoted in (ISO 4217 or crypto code like BTC).
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    # Exchange or market (null for crypto assets).
    market: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    holdings: Mapped[list["Holding"]] = relationship(back_populates="asset")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<Asset ticker={self.ticker!r} name={self.name!r} type={self.asset_type!r}>"
