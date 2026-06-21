"""Pydantic schemas for D04 — FX Calculation Engine API.

The engine is stateless and pure; the API layer accepts current market data
as caller-supplied inputs (D09 will provide these automatically in a later
iteration) and returns the calculated FX metrics for a holding and its lots.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.fx_engine import LotCalcStatus


class FxCalcRequest(BaseModel):
    """Caller-supplied current market data for the holding's asset."""
    current_unit_price: Decimal = Field(gt=0, decimal_places=8)
    fx_rate_current: Decimal = Field(gt=0, decimal_places=8)


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
