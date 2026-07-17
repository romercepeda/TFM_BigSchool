"""Pydantic schemas for Dividend Tracking — Spec D15.

Request/response shapes for /assets/{id}/dividend-schedule and
/portfolios/{id}/holdings/{id}/dividend-payments endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.d03_schemas import FxRateOrigin

DividendFrequency = Literal["monthly", "quarterly", "semiannual", "annual", "irregular"]
DividendScheduleOrigin = Literal["manual", "auto"]
DividendAmountType = Literal["nominal", "percentage"]


# ── AssetDividendSchedule schemas (D15 §3.1, §5.2) ────────────────────────────


class DividendScheduleIn(BaseModel):
    """Upsert body for PUT .../dividend-schedule (D15 §5.2, §8.1).

    amount_type='nominal': amount_per_payment is a currency amount per share
    (quote_currency). amount_type='percentage': amount_per_payment is a plain
    percentage number (e.g. 2.5 for "2.5%") of the current share price —
    lets the user record the dividend exactly as the company announced it,
    without doing the conversion by hand.
    """
    frequency: DividendFrequency
    amount_type: DividendAmountType = "nominal"
    amount_per_payment: Decimal = Field(gt=0, decimal_places=8)
    next_payment_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)


class DividendScheduleResponse(BaseModel):
    id: UUID
    asset_id: UUID
    frequency: str
    amount_type: str
    amount_per_payment: Decimal
    next_payment_date: date | None
    origin: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── DividendPayment schemas (D15 §3.2, §6.2, §8.2) ────────────────────────────


class DividendPaymentIn(BaseModel):
    """Body for POST .../dividend-payments (D15 §6.2)."""
    payment_date: date
    gross_amount_quote: Decimal = Field(gt=0, decimal_places=8)
    fx_rate_at_payment: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    fx_rate_origin: FxRateOrigin = "manual"
    notes: str | None = Field(default=None, max_length=500)


class DividendPaymentPatch(BaseModel):
    """Payments are immutable except notes (D15 §10) — every other field is locked."""
    notes: str | None = Field(default=None, max_length=500)


class DividendPaymentResponse(BaseModel):
    id: UUID
    holding_id: UUID
    payment_date: date
    gross_amount_quote: Decimal
    fx_rate_at_payment: Decimal | None
    fx_rate_origin: str
    gross_amount_base: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
