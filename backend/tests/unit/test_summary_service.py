"""Unit tests for the PortfolioSummary pure aggregation logic — Changeset C08.

Coverage target: 90%+ (Spec 00c — FX/aggregation logic is critical business
logic). Per this project's established convention (see test_settings_api.py),
DB-touching paths (_fetch_holding_snapshots, _fetch_price_series,
_fetch_fx_series, get_summary) are verified manually against the dev
database and are not covered here; every scenario below drives
compute_summary() directly with hand-built snapshots, exactly like
test_fx_engine.py drives calculate_holding().
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.services.summary_service import (
    HoldingSnapshot,
    LotSnapshot,
    _quantity_remaining_at,
    compute_holding_summaries,
    compute_summary,
)

D = Decimal
TODAY = date(2026, 6, 15)
NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

ASSET_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
ASSET_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")
HOLDING_A = UUID("aaaaaaaa-1111-0000-0000-000000000001")
HOLDING_B = UUID("bbbbbbbb-1111-0000-0000-000000000002")
LOT_A = UUID("aaaaaaaa-2222-0000-0000-000000000001")
LOT_B = UUID("bbbbbbbb-2222-0000-0000-000000000002")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _lot(
    lot_id: UUID = LOT_A,
    *,
    purchase_date: date,
    qty: str,
    p_buy: str,
    fx_buy: str | None,
    consumptions: tuple[tuple[date, Decimal], ...] = (),
) -> LotSnapshot:
    return LotSnapshot(
        lot_id=lot_id,
        purchase_date=purchase_date,
        quantity=D(qty),
        unit_price=D(p_buy),
        fx_rate_at_purchase=D(fx_buy) if fx_buy is not None else None,
        consumptions=consumptions,
    )


def _holding(
    holding_id: UUID,
    asset_id: UUID,
    quote_currency: str,
    lots: list[LotSnapshot],
    sales: tuple[tuple[date, Decimal | None], ...] = (),
    dividends: tuple[tuple[date, Decimal | None], ...] = (),
) -> HoldingSnapshot:
    return HoldingSnapshot(
        holding_id=holding_id, asset_id=asset_id, quote_currency=quote_currency, lots=tuple(lots),
        sales=sales, dividend_payments=dividends,
    )


def _flat_series(value: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    """One (date, value) entry per day in [start, end], inclusive."""
    n = (end - start).days
    return [(start + timedelta(days=i), D(value)) for i in range(n + 1)]


_WINDOW_START = TODAY - timedelta(days=29)


# ─── _quantity_remaining_at ───────────────────────────────────────────────────


def test_quantity_remaining_ignores_future_dated_sale() -> None:
    lot = _lot(purchase_date=TODAY - timedelta(days=10), qty="10", p_buy="100", fx_buy="1",
               consumptions=((TODAY + timedelta(days=5), D("3")),))
    assert _quantity_remaining_at(lot, TODAY) == D("10")
    assert _quantity_remaining_at(lot, TODAY + timedelta(days=5)) == D("7")


def test_quantity_remaining_zero_before_purchase_date() -> None:
    lot = _lot(purchase_date=TODAY - timedelta(days=2), qty="10", p_buy="100", fx_buy="1")
    assert _quantity_remaining_at(lot, TODAY - timedelta(days=3)) == D("0")
    assert _quantity_remaining_at(lot, TODAY - timedelta(days=2)) == D("10")


# ─── compute_summary — baseline scenarios (Changeset C08 §3) ─────────────────


def test_no_holdings_returns_all_zero() -> None:
    result = compute_summary([], {}, {}, "EUR", TODAY, NOW)
    assert result.total_value == D("0")
    assert result.total_invested == D("0")
    assert result.unrealized_pnl == D("0")
    assert result.unrealized_pnl_pct == D("0")
    assert result.realized_pnl == D("0")
    assert result.realized_pnl_pct == D("0")
    assert result.dividend_income == D("0")
    assert result.trend_30d == []
    assert result.computed_at == NOW
    assert result.base_currency == "EUR"


def test_one_active_lot_matches_manual_calculation() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.total_invested == D("1000.00000000")
    assert result.total_value == D("1000.00000000")
    assert result.unrealized_pnl == D("0.00000000")
    assert result.unrealized_pnl_pct == D("0.0000")
    assert len(result.trend_30d) == 30
    assert all(p.value == D("1000.00000000") and not p.estimated for p in result.trend_30d)


def test_partially_consumed_lot_reduces_total_invested() -> None:
    sale_date = TODAY - timedelta(days=10)
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(
            purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1",
            consumptions=((sale_date, D("4")),),
        ),
    ])
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    # Only the remaining 6 units count towards today's cost basis and value.
    assert result.total_invested == D("600.00000000")
    assert result.total_value == D("600.00000000")

    before_sale = next(p for p in result.trend_30d if p.date == sale_date - timedelta(days=1))
    after_sale = next(p for p in result.trend_30d if p.date == sale_date)
    assert before_sale.value == D("1000.00000000")
    assert after_sale.value == D("600.00000000")


def test_mixed_currency_applies_fx_consistently() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "USD", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="0.90"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}
    fx_rates = {("USD", "EUR"): _flat_series("0.92", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, fx_rates, "EUR", TODAY, NOW)

    assert result.total_invested == D("900.00000000")   # 10 * 100 * 0.90
    assert result.total_value == D("1012.00000000")      # 10 * 110 * 0.92
    assert result.unrealized_pnl == D("112.00000000")
    assert result.unrealized_pnl_pct == D("0.1244")       # 112 / 900, ROUND_HALF_EVEN 4dp
    assert all(p.value == D("1012.00000000") and not p.estimated for p in result.trend_30d)


def test_trend_shorter_than_30_days_for_new_portfolio() -> None:
    purchase_date = TODAY - timedelta(days=5)
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=purchase_date, qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("100", purchase_date, TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert len(result.trend_30d) == 6  # purchase_date..TODAY inclusive
    assert result.trend_30d[0].date == purchase_date
    assert result.trend_30d[-1].date == TODAY


# ─── compute_summary — missing-data edge cases (Changeset C08 §4) ────────────


def test_missing_price_for_one_day_falls_back_and_marks_estimated() -> None:
    gap_date = TODAY - timedelta(days=5)
    series = [
        (d, v) for d, v in _flat_series("100", _WINDOW_START - timedelta(days=5), TODAY)
        if d != gap_date
    ]
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])

    result = compute_summary([holding], {ASSET_A: series}, {}, "EUR", TODAY, NOW)

    gap_point = next(p for p in result.trend_30d if p.date == gap_date)
    assert gap_point.estimated is True
    assert gap_point.value == D("1000.00000000")  # fallback to previous day's close

    other_point = next(p for p in result.trend_30d if p.date == gap_date - timedelta(days=1))
    assert other_point.estimated is False


def test_holding_never_priced_is_excluded_but_others_still_contribute() -> None:
    priced = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    never_priced = _holding(HOLDING_B, ASSET_B, "EUR", [
        _lot(LOT_B, purchase_date=TODAY - timedelta(days=45), qty="5", p_buy="50", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([priced, never_priced], prices, {}, "EUR", TODAY, NOW)

    assert len(result.trend_30d) == 30
    assert all(p.value == D("1000.00000000") and p.estimated for p in result.trend_30d)


def test_day_with_no_priced_holding_is_omitted_entirely() -> None:
    # Position exists well before the window, but price history only starts
    # partway through — distinct from the zero-remaining-quantity case.
    price_start = TODAY - timedelta(days=10)
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("100", price_start, TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert len(result.trend_30d) == 11  # price_start..TODAY inclusive
    assert result.trend_30d[0].date == price_start


def test_holding_never_priced_excluded_from_current_totals() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    result = compute_summary([holding], {}, {}, "EUR", TODAY, NOW)

    assert result.total_invested == D("0")
    assert result.total_value == D("0")
    assert result.trend_30d == []  # never priced on any day either


def test_mixed_currency_fx_fallback_marks_estimated() -> None:
    gap_date = TODAY - timedelta(days=3)
    fx_series = [
        (d, v) for d, v in _flat_series("0.92", TODAY - timedelta(days=60), TODAY)
        if d != gap_date
    ]
    holding = _holding(HOLDING_A, ASSET_A, "USD", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="0.90"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {("USD", "EUR"): fx_series}, "EUR", TODAY, NOW)

    gap_point = next(p for p in result.trend_30d if p.date == gap_date)
    assert gap_point.estimated is True
    assert gap_point.value == D("1012.00000000")  # fx falls back to previous day's rate


def test_mixed_currency_fx_never_available_excludes_holding_everywhere() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "USD", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="0.90"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.total_value == D("0")
    assert result.total_invested == D("0")
    assert result.trend_30d == []  # no FX rate ever available for USD/EUR


def test_fx_rate_missing_at_purchase_excludes_lot_from_totals_not_from_trend() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy=None),
    ])
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    # Cost basis is unknowable (Spec D04) — excluded from current totals.
    assert result.total_invested == D("0")
    assert result.total_value == D("0")
    # Market value is still tracked in the trend regardless of cost-basis knowledge.
    assert all(p.value == D("1000.00000000") for p in result.trend_30d)


# ─── compute_summary — realized P&L (Changeset C20 §6 / Spec D13 §8) ─────────


def test_realized_pnl_matches_d13_worked_example() -> None:
    """D13 §3.1: L1(30@10, fully consumed), L2(20@15, 5 consumed) -> one sale
    with realized_gain_base=325. total_invested_ever = 300 + 300 = 600."""
    sale_date = TODAY - timedelta(days=5)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [
            _lot(LOT_A, purchase_date=date(2025, 3, 15), qty="30", p_buy="10", fx_buy="1",
                 consumptions=((sale_date, D("30")),)),
            _lot(LOT_B, purchase_date=date(2025, 8, 22), qty="20", p_buy="15", fx_buy="1",
                 consumptions=((sale_date, D("5")),)),
        ],
        sales=((sale_date, D("325")),),
    )
    prices = {ASSET_A: _flat_series("15", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.realized_pnl == D("325.00000000")
    assert result.realized_pnl_pct == D("0.5417")  # 325 / 600


def test_realized_pnl_zero_when_no_sales() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.realized_pnl == D("0.00000000")
    assert result.realized_pnl_pct == D("0.0000")


def test_realized_pnl_excludes_sales_with_unknown_gain() -> None:
    """A sale whose realized_gain_base couldn't be computed (unresolved FX,
    or an un-backfillable pre-D13 sale) is skipped, not treated as zero."""
    d = TODAY - timedelta(days=1)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=date(2025, 1, 1), qty="10", p_buy="10", fx_buy="1",
              consumptions=((d, D("10")),))],
        sales=((d, D("50")), (d, None), (d, D("25"))),
    )
    prices = {ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.realized_pnl == D("75.00000000")  # 50 + 25, None excluded


def test_realized_pnl_excludes_future_dated_sales() -> None:
    """A sale dated after `today` hasn't happened yet — its gain must not be
    counted while its units still count as held on the unrealized side."""
    past = TODAY - timedelta(days=1)
    future = TODAY + timedelta(days=1)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=date(2025, 1, 1), qty="20", p_buy="10", fx_buy="1",
              consumptions=((past, D("5")), (future, D("5"))))],
        sales=((past, D("30")), (future, D("999"))),
    )
    prices = {ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.realized_pnl == D("30.00000000")  # only the past-dated sale counts


def test_realized_pnl_aggregates_across_holdings_and_mixed_currency() -> None:
    d = TODAY - timedelta(days=1)
    holding_a = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(LOT_A, purchase_date=date(2025, 1, 1), qty="10", p_buy="10", fx_buy="1")],
        sales=((d, D("100")),),
    )
    holding_b = _holding(
        HOLDING_B, ASSET_B, "USD",
        [_lot(LOT_B, purchase_date=date(2025, 1, 1), qty="5", p_buy="20", fx_buy="0.90")],
        sales=((d, D("50")),),
    )
    prices = {
        ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY),
        ASSET_B: _flat_series("20", TODAY - timedelta(days=60), TODAY),
    }
    fx_rates = {("USD", "EUR"): _flat_series("0.90", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding_a, holding_b], prices, fx_rates, "EUR", TODAY, NOW)

    # total_invested_ever = (10*10*1) + (5*20*0.90) = 100 + 90 = 190
    assert result.realized_pnl == D("150.00000000")  # 100 + 50
    assert result.realized_pnl_pct == D("0.7895")  # 150 / 190


def test_total_invested_ever_counts_fully_consumed_lots() -> None:
    """A fully consumed lot contributes nothing to today's total_invested
    (unrealized side) but still counts in full towards total_invested_ever —
    the denominator for realized_pnl_pct is about capital ever committed."""
    d = TODAY - timedelta(days=1)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=date(2025, 1, 1), qty="10", p_buy="10", fx_buy="1",
              consumptions=((d, D("10")),))],
        sales=((d, D("40")),),
    )
    prices = {ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.total_invested == D("0.00000000")  # fully sold, nothing held today
    assert result.realized_pnl_pct == D("0.4000")  # 40 / (10*10*1) = 40 / 100


def test_total_invested_ever_excludes_lot_with_unresolved_fx() -> None:
    d = TODAY - timedelta(days=1)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=date(2025, 1, 1), qty="10", p_buy="10", fx_buy=None)],
        sales=((d, D("40")),),
    )
    prices = {ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    # total_invested_ever would be 0 (only lot has no fx_rate_at_purchase) -> pct falls back to 0.
    assert result.realized_pnl == D("40.00000000")
    assert result.realized_pnl_pct == D("0.0000")


# ─── compute_holding_summaries — per-holding P&L rows (D13 §10, C20 §8) ──────


def test_holding_summary_active_position_matches_manual_calculation() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, {}, "EUR", TODAY)

    assert row.holding_id == HOLDING_A
    assert row.active_units == D("10.00000000")
    assert row.invested == D("1000.00000000")
    assert row.unrealized_pnl == D("100.00000000")
    assert row.realized_pnl == D("0.00000000")
    assert row.total_pnl == D("100.00000000")
    assert row.total_pnl_pct == D("0.1000")


def test_holding_summary_sold_out_shows_only_realized_pnl() -> None:
    """D13 §10: active_units == 0 -> invested/unrealized read as zero, only
    realized_pnl carries the "Sold" row's figure."""
    d = TODAY - timedelta(days=10)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1",
              consumptions=((d, D("10")),))],
        sales=((d, D("40")),),
    )
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, {}, "EUR", TODAY)

    assert row.active_units == D("0.00000000")
    assert row.invested == D("0.00000000")
    assert row.unrealized_pnl == D("0.00000000")
    assert row.realized_pnl == D("40.00000000")
    assert row.total_pnl == D("40.00000000")
    assert row.total_pnl_pct == D("0.0000")  # invested is 0 — pct doesn't apply, not divided


def test_holding_summary_never_priced_reads_invested_and_unrealized_as_zero() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])

    [row] = compute_holding_summaries([holding], {}, {}, "EUR", TODAY)

    assert row.invested == D("0.00000000")
    assert row.unrealized_pnl == D("0.00000000")


def test_holding_summary_cross_currency_matches_manual_calculation() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "USD", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="0.90"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}
    fx_rates = {("USD", "EUR"): _flat_series("0.92", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, fx_rates, "EUR", TODAY)

    assert row.invested == D("900.00000000")
    assert row.unrealized_pnl == D("112.00000000")


def test_holding_summary_fx_unavailable_reads_invested_and_unrealized_as_zero() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "USD", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="0.90"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, {}, "EUR", TODAY)  # no USD/EUR series

    assert row.invested == D("0.00000000")
    assert row.unrealized_pnl == D("0.00000000")


def test_holding_summary_excludes_future_dated_sale() -> None:
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1")],
        sales=((TODAY + timedelta(days=1), D("999")),),
    )
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, {}, "EUR", TODAY)

    assert row.realized_pnl == D("0.00000000")


def test_holding_summaries_return_one_row_per_holding_not_aggregated() -> None:
    holding_a = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(LOT_A, purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    holding_b = _holding(HOLDING_B, ASSET_B, "EUR", [
        _lot(LOT_B, purchase_date=TODAY - timedelta(days=45), qty="5", p_buy="50", fx_buy="1"),
    ])
    prices = {
        ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY),
        ASSET_B: _flat_series("60", TODAY - timedelta(days=60), TODAY),
    }

    rows = compute_holding_summaries([holding_a, holding_b], prices, {}, "EUR", TODAY)

    assert [r.holding_id for r in rows] == [HOLDING_A, HOLDING_B]
    assert rows[0].invested == D("1000.00000000")
    assert rows[1].invested == D("250.00000000")
    assert rows[1].unrealized_pnl == D("50.00000000")  # (60-50)*5


# ─── dividend_income (Spec D15 §7) ────────────────────────────────────────────


def test_dividend_income_zero_when_no_payments() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("100", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.dividend_income == D("0.00000000")


def test_dividend_income_sums_payments_across_holdings() -> None:
    d = TODAY - timedelta(days=5)
    holding_a = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(LOT_A, purchase_date=date(2025, 1, 1), qty="10", p_buy="10", fx_buy="1")],
        dividends=((d, D("15")),),
    )
    holding_b = _holding(
        HOLDING_B, ASSET_B, "EUR",
        [_lot(LOT_B, purchase_date=date(2025, 1, 1), qty="5", p_buy="20", fx_buy="1")],
        dividends=((d, D("5")),),
    )
    prices = {
        ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY),
        ASSET_B: _flat_series("20", TODAY - timedelta(days=60), TODAY),
    }

    result = compute_summary([holding_a, holding_b], prices, {}, "EUR", TODAY, NOW)

    assert result.dividend_income == D("20.00000000")


def test_dividend_income_excludes_unknown_gain_and_future_dated_payments() -> None:
    past = TODAY - timedelta(days=1)
    future = TODAY + timedelta(days=1)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=date(2025, 1, 1), qty="10", p_buy="10", fx_buy="1")],
        dividends=((past, D("10")), (past, None), (future, D("999"))),
    )
    prices = {ASSET_A: _flat_series("10", TODAY - timedelta(days=60), TODAY)}

    result = compute_summary([holding], prices, {}, "EUR", TODAY, NOW)

    assert result.dividend_income == D("10.00000000")


def test_holding_summary_dividend_income_included_in_total_pnl() -> None:
    d = TODAY - timedelta(days=5)
    holding = _holding(
        HOLDING_A, ASSET_A, "EUR",
        [_lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1")],
        dividends=((d, D("20")),),
    )
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, {}, "EUR", TODAY)

    assert row.dividend_income == D("20.00000000")
    assert row.unrealized_pnl == D("100.00000000")
    assert row.total_pnl == D("120.00000000")  # unrealized + dividend_income, no sales


def test_holding_summary_dividend_coverage_years_matches_worked_example() -> None:
    """Spec D15 §4.2: avg cost EUR8, annual dividend EUR1/share -> 8 years."""
    from app.db.models.dividend import AssetDividendSchedule

    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(LOT_A, purchase_date=date(2025, 1, 1), qty="1", p_buy="10", fx_buy="1"),
        _lot(LOT_B, purchase_date=date(2025, 6, 1), qty="1", p_buy="6", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("15", TODAY - timedelta(days=60), TODAY)}
    schedule = AssetDividendSchedule(
        asset_id=ASSET_A, frequency="annual", amount_per_payment=D("1"),
    )

    [row] = compute_holding_summaries(
        [holding], prices, {}, "EUR", TODAY, schedules={ASSET_A: schedule}
    )

    assert row.dividend_coverage_years == D("8.00")


def test_holding_summary_dividend_coverage_years_none_without_schedule() -> None:
    holding = _holding(HOLDING_A, ASSET_A, "EUR", [
        _lot(purchase_date=TODAY - timedelta(days=45), qty="10", p_buy="100", fx_buy="1"),
    ])
    prices = {ASSET_A: _flat_series("110", TODAY - timedelta(days=60), TODAY)}

    [row] = compute_holding_summaries([holding], prices, {}, "EUR", TODAY)

    assert row.dividend_coverage_years is None
