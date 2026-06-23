"""Pydantic schemas for D04 — FX Calculation Engine API.

With D09 implemented, current_unit_price and fx_rate_current are optional:
omit them to have the server resolve them automatically via the market data
service. Supply them explicitly to override (manual mode / testing).
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.fx_engine import LotCalcStatus


class FxCalcRequest(BaseModel):
    """Current market data for the holding's asset.

    Both fields are optional: if omitted, D09 resolves them automatically.
    If provided, the caller-supplied values are used as-is (override mode).
    """
    current_unit_price: Decimal | None = Field(default=None, gt=0, decimal_places=8)
    fx_rate_current: Decimal | None = Field(default=None, gt=0, decimal_places=8)


class LotCalcResponse(BaseModel):
    """Per-lot calculation result (Spec D04 §5)."""
    lot_id: UUID
    status: LotCalcStatus
    cost_quote: Decimal | None = None
    cost_base: Decimal | None = None
    current_value_quote: Decimal | None = None
    current_value_base: Decimal | None = None
    asset_return: Decimal | None = None
    base_return: Decimal | None = None
    fx_effect: Decimal | None = None


class HoldingCalcResponse(BaseModel):
    """Aggregated FX calculation result for a holding (Spec D04 §6)."""
    holding_id: UUID
    has_fx_missing: bool
    total_cost_quote: Decimal | None = None
    total_cost_base: Decimal | None = None
    total_value_quote: Decimal | None = None
    total_value_base: Decimal | None = None
    asset_return_total: Decimal | None = None
    base_return_total: Decimal | None = None
    fx_effect_total: Decimal | None = None
    lots: list[LotCalcResponse]
