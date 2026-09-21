"""Pydantic schemas for D06 — Price Levels, Alert Engine & Analysis History."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.date_alert_schemas import PortfolioDateAlertItem

Direction = Literal["buy", "sell"]
LevelStatus = Literal["armed", "touched"]
EventType = Literal["created", "edited", "touched", "removed"]


# ── Request schemas ───────────────────────────────────────────────────────────


class PriceLevelIn(BaseModel):
    """One price level in a batch-create request (Spec D06 §8).

    valid_until is required (2026-09 changeset): the cutoff date the
    condition must be met by to count as "on time" rather than a late,
    retrospective-only crossing. Service layer also rejects a past date.
    """
    direction: Direction
    target_price: Decimal = Field(gt=0, decimal_places=8)
    note: str | None = None
    valid_until: date


class PriceLevelBatchIn(BaseModel):
    """Body for POST .../price-levels: one or more levels in a single submission."""
    levels: list[PriceLevelIn] = Field(min_length=1)
    asset_price_at_event: Decimal | None = Field(default=None, gt=0, decimal_places=8)


class PriceLevelPatch(BaseModel):
    """PATCH body — only provided fields are updated.

    direction, target_price, and valid_until are rejected when the level is
    'touched' (Spec D06 §3.2; valid_until per the 2026-09 changeset).
    """
    direction: Direction | None = None
    target_price: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    note: str | None = None
    valid_until: date | None = None
    asset_price_at_event: Decimal | None = Field(default=None, gt=0, decimal_places=8)


class PriceLevelDeleteRequest(BaseModel):
    """Optional asset price at the time of deletion (used for history snapshot)."""
    asset_price_at_event: Decimal | None = Field(default=None, gt=0, decimal_places=8)


class EvaluateRequest(BaseModel):
    """Manual trigger for the alert crossing logic (Spec D06 §5.2).

    In production this is called by the D09 daily price-update job.
    This endpoint exists for testing before D09 is available.
    """
    previous_close: Decimal = Field(gt=0, decimal_places=8)
    current_close: Decimal = Field(gt=0, decimal_places=8)
    close_date: date
    asset_price_at_event: Decimal | None = Field(default=None, gt=0, decimal_places=8)


# ── Response schemas ──────────────────────────────────────────────────────────


class PriceLevelResponse(BaseModel):
    id: UUID
    holding_id: UUID
    direction: str
    target_price: Decimal
    note: str | None
    # Null only on the handful of levels created before this field existed
    # (2026-09 changeset) — treated as "no expiry defined".
    valid_until: date | None
    status: str
    created_at: datetime
    updated_at: datetime
    touched_at: datetime | None
    touched_at_close_price: Decimal | None
    touched_at_close_date: date | None
    # None while armed. True if touched with no valid_until, or touched on/
    # before it. False if touched after it — a late, retrospective-only
    # crossing (2026-09 changeset; drives the green/gray shading).
    touched_within_validity: bool | None
    # Null = unread alert. Only meaningful while status = 'touched' (Changeset C12).
    alert_seen_at: datetime | None

    model_config = {"from_attributes": True}


class PriceLevelHistoryEntryResponse(BaseModel):
    id: UUID
    holding_id: UUID
    originating_level_id: UUID
    event_type: str
    event_at: datetime
    direction: str
    target_price: Decimal
    note: str | None
    valid_until: date | None
    asset_price_at_event: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvaluateResponse(BaseModel):
    """Result of evaluating alert crossings for a holding."""
    holding_id: UUID
    levels_touched: list[PriceLevelResponse]
    levels_evaluated: int


class PortfolioAlertItem(PriceLevelResponse):
    """A price level enriched with asset context, for the portfolio-wide Alerts Panel (Spec D06 §6)."""
    asset_ticker: str
    asset_name: str
    asset_quote_currency: str
    current_price: Decimal | None
    # Fraction of current_price separating it from target_price. Only set for
    # 'near_crossing' items — armed levels within alerts.near_crossing_pct (§12).
    gap_pct: float | None


class PortfolioAlertsResponse(BaseModel):
    """Consolidated alerts for a portfolio (Spec D06 §6, extended by Changeset C17).

    touched: crossed levels, most recently touched first.
    near_crossing: armed levels within the configured proximity threshold,
    closest gap first.
    date_due: date alerts whose date has arrived, most recently due first.
    date_upcoming: date alerts within alerts.date_upcoming_days, soonest first.
    """
    touched: list[PortfolioAlertItem]
    near_crossing: list[PortfolioAlertItem]
    date_due: list[PortfolioDateAlertItem]
    date_upcoming: list[PortfolioDateAlertItem]
    # Sum of unread `touched` price levels and unread `date_due` alerts
    # (Changeset C12, extended by Changeset C17) — one number for the dashboard badge.
    unread_count: int
