"""Unit tests for the FIFO + realized-gain computation — Spec D13 §3/§4.2/§7.1,
Changeset C20 §2/§3.

Coverage target: 90%+ (Spec 00c — this is critical business logic; errors here
directly produce incorrect tax-relevant figures). Per this project's
established convention (see test_summary_service.py, test_fx_engine.py),
DB-touching paths (create_sale, update_reason, delete_sale,
compute_fifo_preview's lot fetch) are verified manually against the dev
database (Spec 00c §2, §7) rather than covered here; every scenario below
drives compute_fifo()/compute_sale_preview() directly — pure, no I/O. Lot
instances are hand-built and never added to a session, so this stays free of
any database dependency.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.db.models.lot import Lot
from app.services.sale_service import (
    InsufficientUnitsError,
    compute_fifo,
    compute_sale_preview,
)

D = Decimal
HOLDING_ID = uuid4()


def _lot(
    *,
    lot_id: UUID | None = None,
    purchase_date: date,
    qty: str,
    price: str,
    fx: str | None,
    consumed: str = "0",
) -> Lot:
    return Lot(
        id=lot_id or uuid4(),
        holding_id=HOLDING_ID,
        purchase_date=purchase_date,
        quantity=D(qty),
        unit_price=D(price),
        fx_rate_at_purchase=D(fx) if fx is not None else None,
        fx_rate_origin="manual",
        quantity_consumed=D(consumed),
    )


# ─── D13 §3.1 worked example ─────────────────────────────────────────────────


def test_worked_example_matches_spec_d13() -> None:
    """L1: 30@10 (2025-03-15), L2: 20@15 (2025-08-22). Sell 35 units.

    Expected: L1 fully consumed (30@10=300), L2 partially (5@15=75),
    cost_basis_quote = 375.
    """
    l1 = _lot(purchase_date=date(2025, 3, 15), qty="30", price="10", fx=None)
    l2 = _lot(purchase_date=date(2025, 8, 22), qty="20", price="15", fx=None)

    result = compute_fifo([l1, l2], D("35"))

    assert result.insufficient is False
    assert result.cost_basis_quote == D("375.00000000")
    assert len(result.consumptions) == 2
    assert result.consumptions[0].lot_id == l1.id
    assert result.consumptions[0].units_consumed == D("30")
    assert result.consumptions[0].cost_contribution == D("300.00000000")
    assert result.consumptions[1].lot_id == l2.id
    assert result.consumptions[1].units_consumed == D("5")
    assert result.consumptions[1].cost_contribution == D("75.00000000")


# ─── Single-lot and multi-lot boundaries ─────────────────────────────────────


def test_sells_exactly_first_lot_leaves_second_untouched() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="20", fx=None)
    l2 = _lot(purchase_date=date(2025, 2, 1), qty="10", price="25", fx=None)

    result = compute_fifo([l1, l2], D("10"))

    assert len(result.consumptions) == 1
    assert result.consumptions[0].lot_id == l1.id
    assert result.consumptions[0].units_consumed == D("10")
    assert result.cost_basis_quote == D("200.00000000")


def test_sells_exactly_all_remaining_across_three_lots() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="5", price="10", fx=None)
    l2 = _lot(purchase_date=date(2025, 2, 1), qty="5", price="12", fx=None)
    l3 = _lot(purchase_date=date(2025, 3, 1), qty="5", price="14", fx=None)

    result = compute_fifo([l1, l2, l3], D("15"))

    assert len(result.consumptions) == 3
    assert all(c.units_consumed == D("5") for c in result.consumptions)
    assert result.units_available == D("15")
    total_consumed = sum(c.units_consumed for c in result.consumptions)
    assert total_consumed == D("15")


def test_already_fully_consumed_lot_is_skipped() -> None:
    """A lot passed in with quantity_consumed == quantity (available = 0)
    contributes nothing even if positioned before a lot with room."""
    exhausted = _lot(purchase_date=date(2025, 1, 1), qty="10", price="10", fx=None, consumed="10")
    available = _lot(purchase_date=date(2025, 2, 1), qty="10", price="20", fx=None)

    result = compute_fifo([exhausted, available], D("4"))

    assert len(result.consumptions) == 1
    assert result.consumptions[0].lot_id == available.id
    assert result.consumptions[0].units_consumed == D("4")


# ─── Oversell ─────────────────────────────────────────────────────────────────


def test_oversell_reports_insufficient_with_no_partial_consumption() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="10", fx=None)

    result = compute_fifo([l1], D("11"))

    assert result.insufficient is True
    assert result.units_available == D("10")
    assert result.consumptions == ()
    assert result.cost_basis_quote == D("0")
    assert result.cost_basis_base is None


def test_insufficient_units_error_carries_available_and_requested() -> None:
    err = InsufficientUnitsError(D("10"), D("11"))
    assert err.units_available == D("10")
    assert err.units_requested == D("11")
    assert "10" in str(err) and "11" in str(err)


# ─── Cross-currency (base) cost basis ────────────────────────────────────────


def test_cross_currency_cost_basis_base_uses_each_lots_own_fx_rate() -> None:
    """Portfolio EUR, asset USD: cost_basis_base respects each lot's own
    fx_rate_at_purchase (D13 §4.1), not a single blended rate."""
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="100", fx="0.90")
    l2 = _lot(purchase_date=date(2025, 6, 1), qty="10", price="120", fx="0.95")

    result = compute_fifo([l1, l2], D("15"))

    # quote: (10 @ 100) + (5 @ 120) = 1600 ; base: (10 @ 100 * 0.90) + (5 @ 120 * 0.95) = 1470
    assert result.cost_basis_quote == D("1600.00000000")
    assert result.cost_basis_base == D("1470.00000000")


def test_missing_fx_rate_on_any_consumed_lot_leaves_base_none() -> None:
    """One consumed lot lacking fx_rate_at_purchase (manual_pending) voids the
    whole base-currency figure rather than silently understating it."""
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="100", fx="0.90")
    l2 = _lot(purchase_date=date(2025, 6, 1), qty="10", price="120", fx=None)

    result = compute_fifo([l1, l2], D("15"))

    assert result.cost_basis_quote == D("1600.00000000")  # quote-currency unaffected
    assert result.cost_basis_base is None


# ─── Rounding ─────────────────────────────────────────────────────────────────


def test_cost_basis_rounds_half_even_to_eight_decimal_places() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="3", price="10.333333335", fx=None)

    result = compute_fifo([l1], D("3"))

    # Exact product is 31.000000005 — a tie at the 8th decimal place (preceding
    # digit 0 is even), so ROUND_HALF_EVEN rounds down to 31.00000000.
    assert result.cost_basis_quote == D("31.00000000")
    assert result.cost_basis_quote.as_tuple().exponent == -8


# ─── compute_sale_preview (Spec D13 §7.1, §3) ─────────────────────────────────


def test_preview_worked_example_matches_spec_d13() -> None:
    """D13 §3.1: 35 units @ €20 against L1(30@10)/L2(20@15) -> proceeds 700,
    cost basis 375, realized gain +325."""
    l1 = _lot(purchase_date=date(2025, 3, 15), qty="30", price="10", fx=None)
    l2 = _lot(purchase_date=date(2025, 8, 22), qty="20", price="15", fx=None)
    fifo = compute_fifo([l1, l2], D("35"))

    preview = compute_sale_preview(fifo, D("35"), D("20"), fx_rate_at_sale=None)

    assert preview.sale_proceeds_quote == D("700.00000000")
    assert preview.realized_gain_quote == D("325.00000000")
    assert preview.sale_proceeds_base is None  # no fx_rate_at_sale provided
    assert preview.realized_gain_base is None


def test_preview_reports_a_loss_as_a_negative_realized_gain() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="50", fx=None)
    fifo = compute_fifo([l1], D("10"))

    preview = compute_sale_preview(fifo, D("10"), D("40"), fx_rate_at_sale=None)

    assert preview.sale_proceeds_quote == D("400.00000000")
    assert preview.realized_gain_quote == D("-100.00000000")


def test_preview_computes_base_currency_when_fx_available() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="100", fx="0.90")
    fifo = compute_fifo([l1], D("10"))

    preview = compute_sale_preview(fifo, D("10"), D("120"), fx_rate_at_sale=D("0.92"))

    assert preview.sale_proceeds_base == D("1104.00000000")  # 10*120*0.92
    assert preview.realized_gain_base == D("204.00000000")  # 1104 - (10*100*0.90)


def test_preview_insufficient_units_reports_no_gain_figures() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="5", price="10", fx=None)
    fifo = compute_fifo([l1], D("999"))

    preview = compute_sale_preview(fifo, D("999"), D("20"), fx_rate_at_sale=D("1"))

    assert preview.fifo.insufficient is True
    assert preview.realized_gain_quote is None
    assert preview.sale_proceeds_base is None
    assert preview.realized_gain_base is None


def test_preview_leaves_base_none_when_a_consumed_lot_has_no_fx_rate() -> None:
    l1 = _lot(purchase_date=date(2025, 1, 1), qty="10", price="100", fx=None)
    fifo = compute_fifo([l1], D("10"))

    preview = compute_sale_preview(fifo, D("10"), D("120"), fx_rate_at_sale=D("0.92"))

    assert preview.sale_proceeds_quote == D("1200.00000000")
    assert preview.realized_gain_quote == D("200.00000000")
    assert preview.sale_proceeds_base is None
    assert preview.realized_gain_base is None
