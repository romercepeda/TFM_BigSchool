"""Unit tests for dividend_service's pure computation — Spec D15 §4.

Coverage target: compute_dividend_coverage_years() edge cases per D15 §4.3.
DB-touching paths (schedule/payment CRUD, the DateAlert fan-out) are verified
manually against the dev database, same convention as sale_service/
summary_service (Spec 00c).
"""

from decimal import Decimal
from uuid import UUID

from app.db.models.dividend import AssetDividendSchedule
from app.services.dividend_service import compute_dividend_coverage_years

D = Decimal
ASSET_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")


def _schedule(frequency: str, amount: str, amount_type: str = "nominal") -> AssetDividendSchedule:
    return AssetDividendSchedule(
        asset_id=ASSET_A, frequency=frequency, amount_type=amount_type, amount_per_payment=D(amount)
    )


def test_matches_worked_example_from_spec() -> None:
    """D15 §4.2: avg cost EUR8, annual dividend EUR1/share -> 8 years."""
    result = compute_dividend_coverage_years(D("8"), _schedule("annual", "1"), D("1"))
    assert result == D("8.00")


def test_quarterly_frequency_annualizes_to_four_payments() -> None:
    # avg cost 20, EUR0.50/quarter -> annualized EUR2 -> 10 years.
    result = compute_dividend_coverage_years(D("20"), _schedule("quarterly", "0.50"), D("1"))
    assert result == D("10.00")


def test_monthly_frequency_annualizes_to_twelve_payments() -> None:
    # avg cost 12, EUR1/month -> annualized EUR12 -> 1 year.
    result = compute_dividend_coverage_years(D("12"), _schedule("monthly", "1"), D("1"))
    assert result == D("1.00")


def test_applies_current_fx_rate_for_cross_currency_asset() -> None:
    # avg cost base EUR9, dividend USD1/share annual, fx 0.90 -> annualized base EUR0.90 -> 10 years.
    result = compute_dividend_coverage_years(D("9"), _schedule("annual", "1"), D("0.90"))
    assert result == D("10.00")


def test_none_when_no_schedule_declared() -> None:
    assert compute_dividend_coverage_years(D("8"), None, D("1")) is None


def test_none_for_irregular_frequency() -> None:
    assert compute_dividend_coverage_years(D("8"), _schedule("irregular", "1"), D("1")) is None


def test_none_when_avg_purchase_price_is_zero() -> None:
    """Sold-out holding (active_units=0) reads avg cost as zero — N/A, not a divide-by-zero."""
    assert compute_dividend_coverage_years(D("0"), _schedule("annual", "1"), D("1")) is None


def test_none_when_annualized_dividend_is_zero() -> None:
    """A suspended dividend (declared amount 0) must not divide by zero."""
    assert compute_dividend_coverage_years(D("8"), _schedule("annual", "0"), D("1")) is None


def test_none_when_current_fx_rate_unresolved() -> None:
    assert compute_dividend_coverage_years(D("8"), _schedule("annual", "1"), None) is None


# ─── amount_type='percentage' (user feedback: register as % of current price) ─


def test_percentage_type_converts_using_current_price() -> None:
    # Declared as "2%" annual, current price EUR50 -> nominal EUR1.00/share/year.
    # avg cost EUR8 -> 8 / 1.00 = 8 years, matching the nominal worked example.
    schedule = _schedule("annual", "2", amount_type="percentage")
    result = compute_dividend_coverage_years(D("8"), schedule, D("1"), current_price_quote=D("50"))
    assert result == D("8.00")


def test_percentage_type_none_without_current_price() -> None:
    schedule = _schedule("annual", "2", amount_type="percentage")
    result = compute_dividend_coverage_years(D("8"), schedule, D("1"), current_price_quote=None)
    assert result is None


def test_percentage_type_none_when_current_price_zero() -> None:
    schedule = _schedule("annual", "2", amount_type="percentage")
    result = compute_dividend_coverage_years(D("8"), schedule, D("1"), current_price_quote=D("0"))
    assert result is None
