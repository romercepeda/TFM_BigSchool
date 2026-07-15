"""Pydantic schemas for D03 — Assets, Holdings, Lots, Sales.

Request/response shapes for /portfolios/{id}/holdings/* and /assets/* endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

FxRateOrigin = Literal["auto", "manual", "corrected", "manual_pending"]
AssetType = Literal["stock", "etf", "fund", "crypto"]


# ── Asset schemas ─────────────────────────────────────────────────────────────


class AssetIn(BaseModel):
    """Asset details provided when adding a new asset to a portfolio."""
    ticker: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    asset_type: AssetType
    quote_currency: str = Field(min_length=1, max_length=10)
    market: str | None = Field(default=None, max_length=64)


class AssetPatch(BaseModel):
    ticker: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    market: str | None = Field(default=None, max_length=64)


class AssetResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    asset_type: str
    quote_currency: str
    market: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Lot schemas ───────────────────────────────────────────────────────────────


class LotIn(BaseModel):
    """Details for a single purchase lot."""
    purchase_date: date
    quantity: Decimal = Field(gt=0, decimal_places=8)
    unit_price: Decimal = Field(gt=0, decimal_places=8)
    fx_rate_at_purchase: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    fx_rate_origin: FxRateOrigin = "manual"
    notes: str | None = None


class LotPatch(BaseModel):
    """All fields optional for PATCH — only provided fields are updated."""
    purchase_date: date | None = None
    quantity: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    unit_price: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    fx_rate_at_purchase: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    fx_rate_origin: FxRateOrigin | None = None
    notes: str | None = None


class LotResponse(BaseModel):
    id: UUID
    purchase_date: date
    quantity: Decimal
    unit_price: Decimal
    fx_rate_at_purchase: Decimal | None
    fx_rate_origin: str
    notes: str | None
    quantity_consumed: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Sale schemas ──────────────────────────────────────────────────────────────


class SaleIn(BaseModel):
    """Details for a single sale event."""
    sale_date: date
    quantity: Decimal = Field(gt=0, decimal_places=8)
    unit_price: Decimal = Field(gt=0, decimal_places=8)
    fx_rate_at_sale: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    fx_rate_origin: FxRateOrigin = "manual"
    # D13 §4.1 "reason" field — max 500 characters.
    notes: str | None = Field(default=None, max_length=500)


class SalePatch(BaseModel):
    """Sales are immutable except for the reason (D13 §11) — every other
    field (quantity, price, date, FX) is locked once a sale is created."""
    notes: str | None = Field(default=None, max_length=500)


class SaleLotConsumptionResponse(BaseModel):
    lot_id: UUID
    quantity_consumed: Decimal

    model_config = {"from_attributes": True}


class SaleResponse(BaseModel):
    id: UUID
    sale_date: date
    quantity: Decimal
    unit_price: Decimal
    fx_rate_at_sale: Decimal | None
    fx_rate_origin: str
    notes: str | None
    # Realized-gain fields (Spec D13 §4.1). None only for pre-D13 sales that
    # could not be backfilled (no SaleLotConsumption history).
    cost_basis_quote: Decimal | None
    cost_basis_base: Decimal | None
    realized_gain_quote: Decimal | None
    realized_gain_base: Decimal | None
    created_at: datetime
    updated_at: datetime
    lot_consumptions: list[SaleLotConsumptionResponse]

    model_config = {"from_attributes": True}


class LotConsumptionPreview(BaseModel):
    """One lot's contribution to a proposed sale (Spec D13 §7.1)."""
    lot_id: UUID
    purchase_date: date
    units_consumed: Decimal
    unit_price: Decimal
    cost_contribution: Decimal


class SalePreviewOut(BaseModel):
    """Read-only FIFO + realized-gain preview for a proposed sale (D13 §7.1,
    §5.3) — no sale is created; the frontend shows these exact figures before
    the user confirms.
    """
    insufficient_units: bool
    units_available: Decimal
    lot_consumptions: list[LotConsumptionPreview]
    cost_basis_quote: Decimal
    sale_proceeds_quote: Decimal
    realized_gain_quote: Decimal | None
    quote_currency: str
    # None whenever a consumed lot's fx_rate_at_purchase or fx_rate_at_sale
    # itself is unresolved (manual_pending) — see SaleService.compute_sale_preview.
    cost_basis_base: Decimal | None
    sale_proceeds_base: Decimal | None
    realized_gain_base: Decimal | None
    base_currency: str
    fx_rate_at_sale: Decimal | None
    fx_rate_origin: str


# ── Holding schemas ───────────────────────────────────────────────────────────


class CreateHoldingRequest(BaseModel):
    """Add an asset to a portfolio: asset details + first lot in one atomic operation."""
    asset: AssetIn
    lot: LotIn


class HoldingAggregates(BaseModel):
    """Computed fields derived from lot data (Spec D03 §8)."""
    quantity_held: Decimal
    total_invested_base: Decimal
    avg_purchase_price_quote: Decimal
    avg_purchase_price_base: Decimal


class HoldingSummaryResponse(BaseModel):
    """One row per holding in the portfolio list view."""
    id: UUID
    asset: AssetResponse
    lot_count: int
    sale_count: int
    aggregates: HoldingAggregates
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HoldingDetailResponse(BaseModel):
    """Full detail view: asset + all lots + all sales."""
    id: UUID
    asset: AssetResponse
    lots: list[LotResponse]
    sales: list[SaleResponse]
    aggregates: HoldingAggregates
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
