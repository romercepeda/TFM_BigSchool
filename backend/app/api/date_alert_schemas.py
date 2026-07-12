"""Pydantic schemas for DateAlert — Changeset C17."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

DateAlertStatus = Literal["pending", "due"]


# ── Request schemas ───────────────────────────────────────────────────────────


class DateAlertIn(BaseModel):
    """Body for POST .../date-alerts: a single alert (Changeset C17 §4)."""
    alert_date: date
    description: str = Field(min_length=1, max_length=500)


class DateAlertPatch(BaseModel):
    """PATCH body — only provided fields are updated. Always allowed (Changeset C17 §1)."""
    alert_date: date | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)


# ── Response schemas ──────────────────────────────────────────────────────────


class DateAlertResponse(BaseModel):
    id: UUID
    holding_id: UUID
    alert_date: date
    description: str
    status: DateAlertStatus
    created_at: datetime
    updated_at: datetime
    # Null = unread alert. Only meaningful once status = 'due' (Changeset C17 §3).
    alert_seen_at: datetime | None

    model_config = {"from_attributes": True}


class PortfolioDateAlertItem(DateAlertResponse):
    """A date alert enriched with asset context, for the portfolio-wide Alerts Panel."""
    asset_ticker: str
    asset_name: str
