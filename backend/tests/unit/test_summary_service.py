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
    holding_id: UUID, asset_id: UUID, quote_currency: str, lots: list[LotSnapshot]
) -> HoldingSnapshot:
    return HoldingSnapshot(
        holding_id=holding_id, asset_id=asset_id, quote_currency=quote_currency, lots=tuple(lots)
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
