"""Unit tests for the FX Calculation Engine — Spec D04 §9.

Coverage target: 90-100% (Spec 00c). All 13 mandatory baseline scenarios are
covered here. Expected values were pre-computed by hand / spreadsheet and
stored as fixtures, as required by Spec D04 §9.

FX rate convention: 1 unit of quote currency = fx_rate units of base currency.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.services.fx_engine import (
    HoldingCalcResult,
    LotCalcInput,
    LotCalcResult,
    LotCalcStatus,
    calculate_holding,
    calculate_lot,
)

D = Decimal
LOT_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
LOT_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _lot(
    lot_id: UUID = LOT_A,
    *,
    qty: str = "1",
    p_buy: str,
    fx_buy: str | None,
    p_now: str,
    fx_now: str,
) -> LotCalcInput:
    return LotCalcInput(
        lot_id=lot_id,
        quantity_remaining=D(qty),
        unit_price_at_purchase=D(p_buy),
        fx_rate_at_purchase=D(fx_buy) if fx_buy is not None else None,
        current_unit_price=D(p_now),
        fx_rate_current=D(fx_now),
    )


# ─── Scenario 1 — Same currency, gain (fx_effect = 0) ────────────────────────


def test_lot_same_currency_gain() -> None:
    """Spec D04 §9 scenario 1: quote == base currency, asset up 10 %."""
    inp = _lot(p_buy="100", fx_buy="1.0", p_now="110", fx_now="1.0")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.cost_quote == D("100.00000000")
    assert r.cost_base == D("100.00000000")
    assert r.current_value_quote == D("110.00000000")
    assert r.current_value_base == D("110.00000000")
    assert r.asset_return == D("0.1000")
    assert r.base_return == D("0.1000")
    assert r.fx_effect == D("0.0000")


# ─── Scenario 2 — Same currency, loss (fx_effect = 0) ────────────────────────


def test_lot_same_currency_loss() -> None:
    """Spec D04 §9 scenario 2: quote == base currency, asset down 10 %."""
    inp = _lot(p_buy="100", fx_buy="1.0", p_now="90", fx_now="1.0")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.asset_return == D("-0.1000")
    assert r.base_return == D("-0.1000")
    assert r.fx_effect == D("0.0000")


# ─── Scenario 3 — Different currency, asset gains, FX favorable ───────────────


def test_lot_cross_currency_gain_fx_favorable() -> None:
    """Spec D04 §9 scenario 3: asset +10 %, EUR strengthened → base_return > asset_return.

    Fixture:
        qty=1, p_buy=100 USD, fx_buy=0.90 (1 USD = 0.90 EUR)
        p_now=110 USD, fx_now=0.95
        cost_base = 100 × 0.90 = 90 EUR
        cv_base   = 110 × 0.95 = 104.50 EUR
        base_return = (104.50 - 90) / 90 = 0.1611...
        fx_effect   = 0.1611 - 0.1000 = 0.0611
    """
    inp = _lot(p_buy="100", fx_buy="0.90", p_now="110", fx_now="0.95")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.asset_return == D("0.1000")
    assert r.base_return == D("0.1611")
    assert r.fx_effect == D("0.0611")
    # Identity: base_return = asset_return + fx_effect (Spec D04 §12)
    assert r.base_return == r.asset_return + r.fx_effect


# ─── Scenario 4 — Different currency, asset gains, FX unfavorable ("Intel") ──


def test_lot_cross_currency_gain_fx_unfavorable_intel_example() -> None:
    """Spec D04 §9 scenario 4 — the Intel example.

    Bought at USD 40 when 1 USD = 0.93 EUR. Now USD 42, but 1 USD = 0.82 EUR.
    Asset gained +5 %, but EUR investor lost money because USD weakened sharply.

    Fixture:
        cost_base = 40 × 0.93 = 37.20 EUR
        cv_base   = 42 × 0.82 = 34.44 EUR
        base_return = (34.44 - 37.20) / 37.20 = -2.76 / 37.20 = -0.0742
        fx_effect   = -0.0742 - 0.0500 = -0.1242
    """
    inp = _lot(p_buy="40", fx_buy="0.93", p_now="42", fx_now="0.82")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.cost_base == D("37.20000000")
    assert r.current_value_base == D("34.44000000")
    assert r.asset_return == D("0.0500")
    assert r.base_return == D("-0.0742")
    assert r.fx_effect == D("-0.1242")
    assert r.base_return == r.asset_return + r.fx_effect


# ─── Scenario 5 — Different currency, asset loses, FX favorable ───────────────


def test_lot_cross_currency_loss_fx_favorable() -> None:
    """Spec D04 §9 scenario 5: asset -10 %, but USD strengthened — loss mitigated.

    Fixture:
        qty=1, p_buy=100, fx_buy=0.85, p_now=90, fx_now=0.95
        cost_base = 100 × 0.85 = 85 EUR
        cv_base   = 90 × 0.95 = 85.50 EUR
        asset_return = -0.1000
        base_return  = (85.50 - 85) / 85 = 0.50 / 85 = 0.0059
        fx_effect    = 0.0059 - (-0.1000) = 0.1059
    """
    inp = _lot(p_buy="100", fx_buy="0.85", p_now="90", fx_now="0.95")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.asset_return == D("-0.1000")
    assert r.base_return == D("0.0059")
    assert r.fx_effect == D("0.1059")
    assert r.base_return == r.asset_return + r.fx_effect


# ─── Scenario 6 — Different currency, asset loses, FX unfavorable ─────────────


def test_lot_cross_currency_loss_fx_unfavorable() -> None:
    """Spec D04 §9 scenario 6: asset -10 %, USD also weakened — double loss.

    Fixture:
        qty=1, p_buy=100, fx_buy=0.95, p_now=90, fx_now=0.85
        cost_base = 100 × 0.95 = 95 EUR
        cv_base   = 90 × 0.85 = 76.50 EUR
        base_return = (76.50 - 95) / 95 = -18.50 / 95 = -0.1947
        fx_effect   = -0.1947 - (-0.1000) = -0.0947
    """
    inp = _lot(p_buy="100", fx_buy="0.95", p_now="90", fx_now="0.85")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.asset_return == D("-0.1000")
    assert r.base_return == D("-0.1947")
    assert r.fx_effect == D("-0.0947")
    assert r.base_return == r.asset_return + r.fx_effect


# ─── Scenario 7 — Asset return = 0, FX moved ─────────────────────────────────


def test_lot_zero_asset_return_fx_moved() -> None:
    """Spec D04 §9 scenario 7: price unchanged, FX moved — fx_effect = base_return.

    Fixture:
        qty=1, p_buy=100, fx_buy=0.90, p_now=100, fx_now=0.95
        cost_base = 100 × 0.90 = 90 EUR
        cv_base   = 100 × 0.95 = 95 EUR
        asset_return = 0.0000
        base_return  = (95 - 90) / 90 = 5/90 = 0.0556
        fx_effect    = 0.0556 (entire return is FX)
    """
    inp = _lot(p_buy="100", fx_buy="0.90", p_now="100", fx_now="0.95")
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.OK
    assert r.asset_return == D("0.0000")
    assert r.base_return == D("0.0556")
    assert r.fx_effect == D("0.0556")
    assert r.base_return == r.asset_return + r.fx_effect


# ─── Scenario 8 — Lot with q_remaining = 0 ───────────────────────────────────


def test_lot_zero_remaining_returns_no_position() -> None:
    """Spec D04 §9 scenario 8: fully consumed lot → ZERO_REMAINING, no figures."""
    inp = LotCalcInput(
        lot_id=LOT_A,
        quantity_remaining=D("0"),
        unit_price_at_purchase=D("100"),
        fx_rate_at_purchase=D("0.93"),
        current_unit_price=D("110"),
        fx_rate_current=D("0.90"),
    )
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.ZERO_REMAINING
    assert r.asset_return is None
    assert r.base_return is None
    assert r.fx_effect is None


# ─── Scenario 9 — Lot with fx_rate_at_purchase = None ────────────────────────


def test_lot_fx_rate_missing_returns_fx_missing_status() -> None:
    """Spec D04 §9 scenario 9: fx_rate_at_purchase not yet provided → FX_RATE_MISSING."""
    inp = LotCalcInput(
        lot_id=LOT_A,
        quantity_remaining=D("5"),
        unit_price_at_purchase=D("100"),
        fx_rate_at_purchase=None,
        current_unit_price=D("110"),
        fx_rate_current=D("0.90"),
    )
    r = calculate_lot(inp)

    assert r.status == LotCalcStatus.FX_RATE_MISSING
    assert r.asset_return is None
    assert r.base_return is None
    assert r.fx_effect is None


# ─── Scenario 10 — Single lot: aggregate equals per-lot ──────────────────────


def test_holding_single_lot_aggregate_equals_per_lot() -> None:
    """Spec D04 §9 scenario 10: one lot → holding-level figures equal lot figures.

    Uses scenario-3 fixture (cross-currency gain, FX favorable).
    """
    inp = _lot(p_buy="100", fx_buy="0.90", p_now="110", fx_now="0.95")
    lot_r = calculate_lot(inp)
    holding_r = calculate_holding([inp])

    assert holding_r.asset_return_total == lot_r.asset_return
    assert holding_r.base_return_total == lot_r.base_return
    assert holding_r.fx_effect_total == lot_r.fx_effect
    assert holding_r.total_cost_quote == lot_r.cost_quote
    assert holding_r.total_cost_base == lot_r.cost_base
    assert holding_r.total_value_quote == lot_r.current_value_quote
    assert holding_r.total_value_base == lot_r.current_value_base
    assert not holding_r.has_fx_missing


# ─── Scenario 11 — Two lots, cost-weighted aggregation ───────────────────────


def test_holding_two_lots_cost_weighted_aggregation() -> None:
    """Spec D04 §9 scenario 11: two lots at different prices and FX rates.

    Lot A: qty=10, p_buy=100, fx_buy=0.90
    Lot B: qty=5,  p_buy=120, fx_buy=0.92
    Current: p_now=115, fx_now=0.93

    Pre-computed fixture values:
        Lot A: asset_return=0.1500, base_return=0.1883, fx_effect=0.0383
        Lot B: asset_return=-0.0417, base_return=-0.0312, fx_effect=0.0105
        Aggregate:
            total_cost_quote  = 1600.00000000
            total_cost_base   = 1452.00000000
            total_value_quote = 1725.00000000
            total_value_base  = 1604.25000000
            asset_return_total = 0.0781  (125/1600)
            base_return_total  = 0.1049  (152.25/1452)
            fx_effect_total    = 0.0268
    The aggregate return lies between the per-lot returns (-0.0312 … 0.1883).
    """
    inp_a = _lot(LOT_A, qty="10", p_buy="100", fx_buy="0.90", p_now="115", fx_now="0.93")
    inp_b = _lot(LOT_B, qty="5",  p_buy="120", fx_buy="0.92", p_now="115", fx_now="0.93")
    r = calculate_holding([inp_a, inp_b])

    # Per-lot results
    lot_a = next(x for x in r.lot_results if x.lot_id == LOT_A)
    lot_b = next(x for x in r.lot_results if x.lot_id == LOT_B)
    assert lot_a.asset_return == D("0.1500")
    assert lot_a.base_return == D("0.1883")
    assert lot_a.fx_effect == D("0.0383")
    assert lot_b.asset_return == D("-0.0417")
    assert lot_b.base_return == D("-0.0312")
    assert lot_b.fx_effect == D("0.0105")

    # Aggregated sums
    assert r.total_cost_quote == D("1600.00000000")
    assert r.total_cost_base == D("1452.00000000")
    assert r.total_value_quote == D("1725.00000000")
    assert r.total_value_base == D("1604.25000000")

    # Aggregated returns
    assert r.asset_return_total == D("0.0781")
    assert r.base_return_total == D("0.1049")
    assert r.fx_effect_total == D("0.0268")

    # Aggregate lies between per-lot returns (cost-weighted, not a simple average)
    assert lot_b.base_return < r.base_return_total < lot_a.base_return  # type: ignore[operator]

    # Identity holds at holding level too
    assert r.base_return_total == r.asset_return_total + r.fx_effect_total
    assert not r.has_fx_missing


# ─── Scenario 12 — Two lots, one fully consumed ───────────────────────────────


def test_holding_one_lot_fully_consumed_excluded_from_aggregation() -> None:
    """Spec D04 §9 scenario 12: consumed lot (q_remaining=0) is excluded.

    Lot A: qty=10, consumed=10 → q_remaining=0 → ZERO_REMAINING (excluded)
    Lot B: qty=5,  consumed=2 → q_remaining=3 → contributes to aggregate

    Fixture (Lot B only, qty_remaining=3):
        p_buy=100, fx_buy=0.90, p_now=110, fx_now=0.95
        asset_return = 0.1000
        base_return  = (3×110×0.95 - 3×100×0.90) / (3×100×0.90)
                     = (313.50 - 270) / 270 = 43.50/270 = 0.1611
        fx_effect    = 0.0611
    """
    inp_a = LotCalcInput(
        lot_id=LOT_A,
        quantity_remaining=D("0"),   # fully consumed
        unit_price_at_purchase=D("100"),
        fx_rate_at_purchase=D("0.90"),
        current_unit_price=D("110"),
        fx_rate_current=D("0.95"),
    )
    inp_b = LotCalcInput(
        lot_id=LOT_B,
        quantity_remaining=D("3"),   # 5 bought - 2 consumed
        unit_price_at_purchase=D("100"),
        fx_rate_at_purchase=D("0.90"),
        current_unit_price=D("110"),
        fx_rate_current=D("0.95"),
    )
    r = calculate_holding([inp_a, inp_b])

    lot_a = next(x for x in r.lot_results if x.lot_id == LOT_A)
    lot_b = next(x for x in r.lot_results if x.lot_id == LOT_B)

    assert lot_a.status == LotCalcStatus.ZERO_REMAINING
    assert lot_b.status == LotCalcStatus.OK

    # Aggregate uses only lot B
    assert r.total_cost_quote == D("300.00000000")   # 3×100
    assert r.total_cost_base == D("270.00000000")    # 3×100×0.90
    assert r.total_value_quote == D("330.00000000")  # 3×110
    assert r.total_value_base == D("313.50000000")   # 3×110×0.95

    assert r.asset_return_total == D("0.1000")
    assert r.base_return_total == D("0.1611")
    assert r.fx_effect_total == D("0.0611")
    assert not r.has_fx_missing


# ─── Scenario 13 — Two lots, one with FX rate missing ─────────────────────────


def test_holding_one_fx_missing_propagates_status_partial_aggregate() -> None:
    """Spec D04 §9 scenario 13: one lot FX rate missing → aggregate from valid lot only.

    Lot A: fx_rate_at_purchase=None → FX_RATE_MISSING (excluded, flag raised)
    Lot B: qty=1, p_buy=100, fx_buy=0.90, p_now=110, fx_now=0.95 → OK

    Fixture (Lot B only):
        asset_return = 0.1000
        base_return  = 0.1611
        fx_effect    = 0.0611
    """
    inp_a = LotCalcInput(
        lot_id=LOT_A,
        quantity_remaining=D("5"),
        unit_price_at_purchase=D("100"),
        fx_rate_at_purchase=None,
        current_unit_price=D("110"),
        fx_rate_current=D("0.95"),
    )
    inp_b = _lot(LOT_B, p_buy="100", fx_buy="0.90", p_now="110", fx_now="0.95")
    r = calculate_holding([inp_a, inp_b])

    lot_a = next(x for x in r.lot_results if x.lot_id == LOT_A)
    lot_b = next(x for x in r.lot_results if x.lot_id == LOT_B)

    assert lot_a.status == LotCalcStatus.FX_RATE_MISSING
    assert lot_b.status == LotCalcStatus.OK

    # has_fx_missing propagates to the holding result
    assert r.has_fx_missing is True

    # Aggregate computed from lot B only
    assert r.asset_return_total == D("0.1000")
    assert r.base_return_total == D("0.1611")
    assert r.fx_effect_total == D("0.0611")
    assert r.total_cost_quote == D("100.00000000")
    assert r.total_cost_base == D("90.00000000")
