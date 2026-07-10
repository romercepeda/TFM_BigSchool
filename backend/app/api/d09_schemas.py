"""Pydantic schemas for D09 — Market & FX Data Integration API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class AssetSearchResultResponse(BaseModel):
    ticker: str
    name: str
    asset_type: Literal["stock", "etf", "fund", "crypto"]
    quote_currency: str
    market: str | None


class PricePointResponse(BaseModel):
    ticker: str
    as_of_date: date
    price: Decimal
    # Changeset C14: execution timestamp — now() for a live fetch, or the
    # stored AssetPriceHistory row's own fetched_at for a last-known fallback.
    fetched_at: datetime


class FxRateResponse(BaseModel):
    quote_currency: str
    base_currency: str
    as_of_date: date
    rate: Decimal
    provider: str


class FxPairSupportedResponse(BaseModel):
    quote_currency: str
    base_currency: str
    supported: bool


class DailyUpdateResponse(BaseModel):
    assets_processed: int
    assets_failed: int
    alerts_triggered: int
    indicator_snapshots: int = 0
    ran_at: datetime
