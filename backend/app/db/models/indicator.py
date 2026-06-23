"""Indicator catalog and historical snapshots — Spec D05.

Two tables:
    Indicator           — seed-file-driven catalog (code is the stable key)
    IndicatorSnapshot   — immutable value log (one row per indicator/subject/date)
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_INDICATOR_SCOPE_ENUM = Enum("asset", "portfolio", name="indicator_scope_enum")
_INDICATOR_NATURE_ENUM = Enum(
    "technical", "fundamental", "portfolio_kpi", name="indicator_nature_enum"
)
_INDICATOR_DATA_TYPE_ENUM = Enum(
    "quantitative", "qualitative", name="indicator_data_type_enum"
)
_INDICATOR_UPDATE_STRATEGY_ENUM = Enum(
    "scheduled_daily", "on_ai_analysis", "on_demand_calculated",
    name="indicator_update_strategy_enum",
)
_SNAPSHOT_SUBJECT_TYPE_ENUM = Enum("asset", "portfolio", name="snapshot_subject_type_enum")
_SNAPSHOT_SOURCE_ENUM = Enum(
    "scheduled_job", "ai_analysis", "on_demand_calc", "manual_override",
    name="snapshot_source_enum",
)


class Indicator(Base):
    __tablename__ = "indicators"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name_key: Mapped[str] = mapped_column(String(128), nullable=False)
    description_key: Mapped[str] = mapped_column(String(256), nullable=False)
    scope: Mapped[str] = mapped_column(_INDICATOR_SCOPE_ENUM, nullable=False)
    nature: Mapped[str] = mapped_column(_INDICATOR_NATURE_ENUM, nullable=False)
    data_type: Mapped[str] = mapped_column(_INDICATOR_DATA_TYPE_ENUM, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    calculator_code: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_extraction_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    update_strategy: Mapped[str] = mapped_column(
        _INDICATOR_UPDATE_STRATEGY_ENUM, nullable=False
    )
    threshold_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    snapshots: Mapped[list["IndicatorSnapshot"]] = relationship(back_populates="indicator")

    def __repr__(self) -> str:
        return f"<Indicator code={self.code!r} scope={self.scope!r} nature={self.nature!r}>"


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "indicator_id", "subject_id", "as_of_date",
            name="uq_snapshot_indicator_subject_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    indicator_id: Mapped[UUID] = mapped_column(
        ForeignKey("indicators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Polymorphic link: subject_type determines whether subject_id points to Asset or Portfolio.
    # No DB-level FK — enforced at the service layer (D05 §5 / ERD implementer note).
    subject_type: Mapped[str] = mapped_column(_SNAPSHOT_SUBJECT_TYPE_ENUM, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=8), nullable=True
    )
    value_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(_SNAPSHOT_SOURCE_ENUM, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    indicator: Mapped["Indicator"] = relationship(back_populates="snapshots")

    def __repr__(self) -> str:
        return (
            f"<IndicatorSnapshot indicator_id={self.indicator_id} "
            f"subject_id={self.subject_id} date={self.as_of_date}>"
        )
