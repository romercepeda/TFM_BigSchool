"""SystemSetting ORM model — Spec D12 §7, Changeset C04 §5.

A minimal global key-value overlay on top of config.yaml. Per Spec 00f §5,
config.yaml is not writable at runtime, so the two admin-editable cascade
lists (market_data.providers, fx_data.providers) are stored here instead;
if a row exists for a key, it wins over config.yaml's value. No other
config key uses this table — this is a narrow, documented exception.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[list] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SystemSetting key={self.key!r} value={self.value!r}>"
