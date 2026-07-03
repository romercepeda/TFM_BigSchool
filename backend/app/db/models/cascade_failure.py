"""CascadeFailureReport and CascadeFailureEntry ORM models — Spec D12 §6.

Persisted at the end of every daily update run (MarketDataService.run_daily_update,
once Changeset C04 Step 7 enables the cascade). Operational/debugging data, not
part of the audit log (D12 §6.3) — rows are hard-deleted after
`market_data.failure_report_retention_days` (default 30).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_FAILURE_REASON_ENUM = Enum(
    "not_found", "rate_limited", "insufficient_lookback", "provider_error",
    name="cascade_failure_reason_enum",
)


class CascadeFailureReport(Base):
    """One row per daily update run. `id` is the run_id in D12 §6.1's JSON shape."""

    __tablename__ = "cascade_failure_reports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    total_assets_processed: Mapped[int] = mapped_column(Integer, nullable=False)
    # {"twelve_data": 38, "eodhd": 3, ...} — D12 §6.1.
    resolved_by_provider: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    failures: Mapped[list["CascadeFailureEntry"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<CascadeFailureReport id={self.id} "
            f"processed={self.total_assets_processed} failures={len(self.failures)}>"
        )


class CascadeFailureEntry(Base):
    """One row per asset that no provider in the cascade could resolve (D12 §6.1)."""

    __tablename__ = "cascade_failure_entries"
    __table_args__ = (
        Index("ix_cascade_failure_entries_asset_id", "asset_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("cascade_failure_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(_FAILURE_REASON_ENUM, nullable=False)
    # ["twelve_data", "eodhd", "finnhub"] — D12 §6.1.
    providers_tried: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # {"twelve_data": "symbol_not_found", ...} — D12 §6.1.
    last_error_by_provider: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    report: Mapped["CascadeFailureReport"] = relationship(back_populates="failures")

    def __repr__(self) -> str:
        return f"<CascadeFailureEntry ticker={self.ticker} reason={self.reason}>"
