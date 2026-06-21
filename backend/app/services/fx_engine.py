"""FX Calculation Engine — Spec D04.

Pure deterministic function: given lot data + current price + current FX rate,
produces asset_return, base_return, and fx_effect for each lot and for the
holding as a whole. No I/O of any kind — no network, no database, no clock.

FX rate convention (Spec D04 §3.1):
    fx_rate = units of base currency per 1 unit of quote currency.
    Example: 1 USD = 0.93 EUR  →  fx_rate = 0.93
    To convert price P (in quote currency) to base currency: P × fx_rate.

All arithmetic uses decimal.Decimal; float is prohibited (Spec D04 §3.2).
Rounding mode: ROUND_HALF_EVEN ("banker's rounding") at 4 dp for returns,
8 dp for monetary cost/value outputs.

The identity base_return = asset_return + fx_effect holds exactly by
construction: fx_effect is always computed as base_return − asset_return
from already-rounded values (Spec D04 §12).
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from uuid import UUID

_Q_RETURN = Decimal("0.0001")       # 4 decimal places: returns and fx_effect
_Q_MONETARY = Decimal("0.00000001") # 8 decimal places: cost/value outputs
_ZERO = Decimal("0")


def _r(value: Decimal, quant: Decimal = _Q_RETURN) -> Decimal:
    """Round value to quant precision with ROUND_HALF_EVEN."""
    return value.quantize(quant, rounding=ROUND_HALF_EVEN)


# ── Public types ──────────────────────────────────────────────────────────────


class LotCalcStatus(str, Enum):
    OK = "ok"
    ZERO_REMAINING = "zero_remaining"
    FX_RATE_MISSING = "fx_rate_missing"


@dataclass(frozen=True)
class LotCalcInput:
    """All inputs required to calculate one lot's FX metrics (Spec D04 §4.1)."""
    lot_id: UUID
    quantity_remaining: Decimal
    unit_price_at_purchase: Decimal
    fx_rate_at_purchase: Decimal | None  # None → status becomes FX_RATE_MISSING
    current_unit_price: Decimal
    fx_rate_current: Decimal


@dataclass(frozen=True)
class LotCalcResult:
    """Per-lot calculation output (Spec D04 §5).

    All Decimal fields are None unless status is OK.
    """
    lot_id: UUID
    status: LotCalcStatus
    cost_quote: Decimal | None = None
    cost_base: Decimal | None = None
    current_value_quote: Decimal | None = None
    current_value_base: Decimal | None = None
    asset_return: Decimal | None = None     # e.g. Decimal("0.0612") = 6.12 %
    base_return: Decimal | None = None
    fx_effect: Decimal | None = None        # in percentage points


@dataclass
class HoldingCalcResult:
    """Holding-level aggregated result across all unconsumed lots (Spec D04 §6).

    Aggregated fields are None if total_cost_quote or total_cost_base is zero
    (no position — Spec D04 §6.3).
    """
    lot_results: list[LotCalcResult] = field(default_factory=list)
    has_fx_missing: bool = False
    total_cost_quote: Decimal | None = None
    total_cost_base: Decimal | None = None
    total_value_quote: Decimal | None = None
    total_value_base: Decimal | None = None
    asset_return_total: Decimal | None = None
    base_return_total: Decimal | None = None
    fx_effect_total: Decimal | None = None


# ── Per-lot calculator ────────────────────────────────────────────────────────


def calculate_lot(inp: LotCalcInput) -> LotCalcResult:
    """Calculate FX metrics for a single lot (Spec D04 §5).

    Returns ZERO_REMAINING if quantity_remaining ≤ 0.
    Returns FX_RATE_MISSING if fx_rate_at_purchase is None.
    Raises ValueError if unit_price_at_purchase ≤ 0 (invariant from D03).
    """
    if inp.quantity_remaining <= _ZERO:
        return LotCalcResult(lot_id=inp.lot_id, status=LotCalcStatus.ZERO_REMAINING)

    if inp.fx_rate_at_purchase is None:
        return LotCalcResult(lot_id=inp.lot_id, status=LotCalcStatus.FX_RATE_MISSING)

    if inp.unit_price_at_purchase <= _ZERO:
        raise ValueError(
            f"Lot {inp.lot_id}: unit_price_at_purchase must be > 0 "
            f"(got {inp.unit_price_at_purchase})."
        )

    q = inp.quantity_remaining
    p_buy = inp.unit_price_at_purchase
    fx_buy = inp.fx_rate_at_purchase
    p_now = inp.current_unit_price
    fx_now = inp.fx_rate_current

    # §5.1 — Cost basis (exact arithmetic; rounded only for output)
    cost_quote_exact = q * p_buy
    cost_base_exact = q * p_buy * fx_buy

    # §5.2 — Current value
    cv_quote_exact = q * p_now
    cv_base_exact = q * p_now * fx_now

    # §5.3 — Returns: computed from exact intermediate values, then rounded
    asset_ret = _r((p_now - p_buy) / p_buy)
    base_ret = _r((cv_base_exact - cost_base_exact) / cost_base_exact)

    # fx_effect from *rounded* returns to preserve the exact identity:
    #   base_return = asset_return + fx_effect  (Spec D04 §12)
    fx_eff = base_ret - asset_ret

    return LotCalcResult(
        lot_id=inp.lot_id,
        status=LotCalcStatus.OK,
        cost_quote=_r(cost_quote_exact, _Q_MONETARY),
        cost_base=_r(cost_base_exact, _Q_MONETARY),
        current_value_quote=_r(cv_quote_exact, _Q_MONETARY),
        current_value_base=_r(cv_base_exact, _Q_MONETARY),
        asset_return=asset_ret,
        base_return=base_ret,
        fx_effect=fx_eff,
    )


# ── Per-holding aggregator ────────────────────────────────────────────────────


def calculate_holding(inputs: list[LotCalcInput]) -> HoldingCalcResult:
    """Aggregate FX metrics across all lots of a holding (Spec D04 §6).

    Only lots with status OK contribute to the aggregate sums (Spec D04 §3.3).
    Lots with ZERO_REMAINING or FX_RATE_MISSING are excluded from aggregation,
    but FX_RATE_MISSING propagates has_fx_missing = True on the result.

    Aggregated returns use cost-weighting naturally via the sums — the formula
    is not a per-lot average but the ratio of total-value to total-cost
    (Spec D04 §6.2).
    """
    lot_results = [calculate_lot(inp) for inp in inputs]
    has_fx_missing = any(r.status == LotCalcStatus.FX_RATE_MISSING for r in lot_results)

    # Accumulate exact sums (no rounding until output) from OK lots only.
    total_cost_q = _ZERO
    total_cost_b = _ZERO
    total_cv_q = _ZERO
    total_cv_b = _ZERO

    for inp, result in zip(inputs, lot_results):
        if result.status != LotCalcStatus.OK:
            continue
        q = inp.quantity_remaining
        # fx_rate_at_purchase is guaranteed non-None when status is OK
        total_cost_q += q * inp.unit_price_at_purchase
        total_cost_b += q * inp.unit_price_at_purchase * inp.fx_rate_at_purchase  # type: ignore[operator]
        total_cv_q += q * inp.current_unit_price
        total_cv_b += q * inp.current_unit_price * inp.fx_rate_current

    if total_cost_q <= _ZERO or total_cost_b <= _ZERO:
        # No remaining position (Spec D04 §6.3).
        return HoldingCalcResult(lot_results=lot_results, has_fx_missing=has_fx_missing)

    # §6.2 — Aggregated returns (cost-weighted by construction)
    asset_ret = _r((total_cv_q - total_cost_q) / total_cost_q)
    base_ret = _r((total_cv_b - total_cost_b) / total_cost_b)
    fx_eff = base_ret - asset_ret  # preserves identity at the aggregate level too

    return HoldingCalcResult(
        lot_results=lot_results,
        has_fx_missing=has_fx_missing,
        total_cost_quote=_r(total_cost_q, _Q_MONETARY),
        total_cost_base=_r(total_cost_b, _Q_MONETARY),
        total_value_quote=_r(total_cv_q, _Q_MONETARY),
        total_value_base=_r(total_cv_b, _Q_MONETARY),
        asset_return_total=asset_ret,
        base_return_total=base_ret,
        fx_effect_total=fx_eff,
    )
