"""Unit tests for D05 — Indicator Catalog & Historical Snapshots.

Covers:
  - Technical calculators: MA200, MA50/200 cross, RSI14, MACD, RVOL stub
  - Zone evaluators: all 6 threshold models from Spec D05 §4

All functions under test are pure (no DB, no I/O).
Expected values were pre-computed by hand. Calculator conventions follow spec §3.3.
"""

from decimal import Decimal

import pytest

from app.services.indicator_service import (
    calc_ma_200,
    calc_ma_50_200_cross,
    calc_macd,
    calc_rsi_14,
    calc_rvol,
    evaluate_zone,
)

D = Decimal


# ── Helpers ───────────────────────────────────────────────────────────────────


def _prices(n: int, value: float = 100.0) -> list[Decimal]:
    """Return a list of n identical prices."""
    return [D(str(value))] * n


def _rising(n: int, start: float = 100.0, step: float = 1.0) -> list[Decimal]:
    return [D(str(start + i * step)) for i in range(n)]


def _falling(n: int, start: float = 100.0, step: float = 1.0) -> list[Decimal]:
    return [D(str(start - i * step)) for i in range(n)]


# ── calc_ma_200 ───────────────────────────────────────────────────────────────


class TestCalcMa200:
    def test_insufficient_data_returns_none(self) -> None:
        """Fewer than 200 prices → silently skip (D05 §6.1)."""
        assert calc_ma_200(_prices(199)) == (None, None)

    def test_exactly_200_identical_prices(self) -> None:
        """200 identical prices → MA equals that price."""
        value, text = calc_ma_200(_prices(200, 150.0))
        assert text is None
        assert value == D("150.0")

    def test_more_than_200_uses_last_200(self) -> None:
        """300 prices where last 200 are all 50.0 — MA uses only those 200."""
        first_100 = _prices(100, 200.0)
        last_200 = _prices(200, 50.0)
        value, text = calc_ma_200(first_100 + last_200)
        assert text is None
        assert value == D("50.0")

    def test_average_computed_correctly(self) -> None:
        """200 prices: 100 of them at 80.0 and 100 at 120.0 → MA = 100.0."""
        prices = _prices(100, 80.0) + _prices(100, 120.0)
        value, _ = calc_ma_200(prices)
        assert value == D("100.0")

    def test_returns_quantitative_not_text(self) -> None:
        """MA200 is quantitative — value_text must always be None."""
        value, text = calc_ma_200(_prices(200))
        assert text is None
        assert value is not None


# ── calc_ma_50_200_cross ──────────────────────────────────────────────────────


class TestCalcMa50200Cross:
    def test_insufficient_data_returns_none(self) -> None:
        """Fewer than 200 prices → silently skip."""
        assert calc_ma_50_200_cross(_prices(199)) == (None, None)

    def test_exactly_200_identical_prices_gives_near_cross(self) -> None:
        """MA50 == MA200 when all prices equal → near_cross."""
        _, text = calc_ma_50_200_cross(_prices(200, 100.0))
        assert text == "near_cross"

    def test_golden_cross_ma50_above_ma200(self) -> None:
        """Last 50 much higher than prior 150 → diff > 2% → golden_cross.

        prices: 150 bars at 100.0, then 50 bars at 110.0
          MA50  = 110.0
          MA200 = (100*150 + 110*50) / 200 = (15000 + 5500) / 200 = 102.5
          diff  = (110 - 102.5) / 102.5 ≈ 0.073 > 0.02 → golden_cross
        """
        prices = _prices(150, 100.0) + _prices(50, 110.0)
        _, text = calc_ma_50_200_cross(prices)
        assert text == "golden_cross"

    def test_death_cross_ma50_below_ma200(self) -> None:
        """Last 50 much lower than prior 150 → diff < -2% → death_cross.

        prices: 150 bars at 100.0, then 50 bars at 90.0
          MA50  = 90.0
          MA200 = (100*150 + 90*50) / 200 = (15000 + 4500) / 200 = 97.5
          diff  = (90 - 97.5) / 97.5 ≈ -0.077 < -0.02 → death_cross
        """
        prices = _prices(150, 100.0) + _prices(50, 90.0)
        _, text = calc_ma_50_200_cross(prices)
        assert text == "death_cross"

    def test_near_cross_within_2pct_band(self) -> None:
        """Small divergence within ±2% → near_cross.

        prices: 150 bars at 100.0, then 50 bars at 101.0
          MA50  = 101.0
          MA200 = (100*150 + 101*50) / 200 = (15000 + 5050) / 200 = 100.25
          diff  = (101 - 100.25) / 100.25 ≈ 0.0075 < 0.02 → near_cross
        """
        prices = _prices(150, 100.0) + _prices(50, 101.0)
        _, text = calc_ma_50_200_cross(prices)
        assert text == "near_cross"

    def test_returns_qualitative_not_numeric(self) -> None:
        """MA50/200 cross is qualitative — value_numeric must always be None."""
        value, text = calc_ma_50_200_cross(_prices(200))
        assert value is None
        assert text is not None


# ── calc_rsi_14 ───────────────────────────────────────────────────────────────


class TestCalcRsi14:
    def test_insufficient_data_fewer_than_15_returns_none(self) -> None:
        """Fewer than 15 prices (need period+1) → silently skip."""
        assert calc_rsi_14(_prices(14)) == (None, None)

    def test_all_gains_returns_100(self) -> None:
        """14 consecutive gains → avg_loss = 0 → RSI = 100."""
        prices = _rising(15, start=100.0, step=1.0)
        value, text = calc_rsi_14(prices)
        assert text is None
        assert value == D("100")

    def test_all_losses_returns_0(self) -> None:
        """14 consecutive losses → avg_gain = 0 → RSI = 0."""
        prices = _falling(15, start=114.0, step=1.0)
        value, text = calc_rsi_14(prices)
        assert text is None
        assert value == D("0")

    def test_equal_gains_and_losses_returns_50(self) -> None:
        """Alternating +1/-1 over 29 changes (30 prices) → RSI ≈ 50.

        With Wilder smoothing, RS → 1 → RSI → 50 over enough iterations.
        We check the value is in the (40, 60) range to avoid floating-point issues.
        """
        prices = []
        p = D("100")
        for i in range(30):
            prices.append(p)
            p += D("1") if i % 2 == 0 else D("-1")
        value, _ = calc_rsi_14(prices)
        assert value is not None
        assert D("40") < value < D("60")

    def test_result_is_within_0_100(self) -> None:
        """RSI is always between 0 and 100 for any price series."""
        prices = _rising(50, start=50.0, step=2.0)
        value, _ = calc_rsi_14(prices)
        assert value is not None
        assert D("0") <= value <= D("100")

    def test_returns_quantitative_not_text(self) -> None:
        value, text = calc_rsi_14(_rising(20))
        assert text is None


# ── calc_macd ─────────────────────────────────────────────────────────────────


class TestCalcMacd:
    def test_insufficient_data_fewer_than_26_returns_none(self) -> None:
        assert calc_macd(_prices(25)) == (None, None)

    def test_identical_prices_returns_zero(self) -> None:
        """EMA12 == EMA26 for constant price series → MACD = 0."""
        value, text = calc_macd(_prices(50, 100.0))
        assert text is None
        assert value is not None
        assert abs(value) < D("0.000001")

    def test_rising_prices_gives_positive_macd(self) -> None:
        """In a rising series EMA12 (reacts faster) > EMA26 → MACD > 0."""
        prices = _rising(50, start=80.0, step=1.0)
        value, _ = calc_macd(prices)
        assert value is not None
        assert value > D("0")

    def test_falling_prices_gives_negative_macd(self) -> None:
        """In a falling series EMA12 < EMA26 → MACD < 0."""
        prices = _falling(50, start=130.0, step=1.0)
        value, _ = calc_macd(prices)
        assert value is not None
        assert value < D("0")

    def test_returns_quantitative_not_text(self) -> None:
        value, text = calc_macd(_prices(30))
        assert text is None


# ── calc_rvol (stub) ──────────────────────────────────────────────────────────


class TestCalcRvol:
    def test_always_returns_none_no_volume_data(self) -> None:
        """RVOL requires volume data not stored in AssetPriceHistory — always skip."""
        assert calc_rvol(_prices(200)) == (None, None)
        assert calc_rvol([]) == (None, None)


# ── evaluate_zone — numeric_thresholds (Spec D05 §4.1) ───────────────────────


class TestEvaluateZoneNumericThresholds:
    """PER: positive <15, neutral 15–25, attention ≥25."""

    CFG = {
        "model": "numeric_thresholds",
        "positive": {"min": None, "max": 15},
        "neutral":  {"min": 15, "max": 25},
        "attention": {"min": 25, "max": None},
    }

    def test_positive_zone(self) -> None:
        assert evaluate_zone(self.CFG, D("10"), None) == "positive"

    def test_neutral_zone(self) -> None:
        assert evaluate_zone(self.CFG, D("20"), None) == "neutral"

    def test_attention_zone(self) -> None:
        assert evaluate_zone(self.CFG, D("30"), None) == "attention"

    def test_boundary_at_positive_max_is_neutral(self) -> None:
        """max is exclusive: value=15 falls into neutral (min=15 inclusive)."""
        assert evaluate_zone(self.CFG, D("15"), None) == "neutral"

    def test_boundary_at_neutral_max_is_attention(self) -> None:
        assert evaluate_zone(self.CFG, D("25"), None) == "attention"

    def test_none_value_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, None) is None


# ── evaluate_zone — three_band_numeric (Spec D05 §4.2) ───────────────────────


class TestEvaluateZoneThreeBandNumeric:
    """RSI: attention <30 | neutral 30–40 | positive 40–70 | neutral 70–80 | attention ≥80."""

    CFG = {
        "model": "three_band_numeric",
        "attention_low":  {"min": None, "max": 30},
        "neutral_low":    {"min": 30, "max": 40},
        "positive":       {"min": 40, "max": 70},
        "neutral_high":   {"min": 70, "max": 80},
        "attention_high": {"min": 80, "max": None},
    }

    def test_attention_low(self) -> None:
        assert evaluate_zone(self.CFG, D("20"), None) == "attention"

    def test_neutral_low(self) -> None:
        assert evaluate_zone(self.CFG, D("35"), None) == "neutral"

    def test_positive(self) -> None:
        assert evaluate_zone(self.CFG, D("55"), None) == "positive"

    def test_neutral_high(self) -> None:
        assert evaluate_zone(self.CFG, D("75"), None) == "neutral"

    def test_attention_high(self) -> None:
        assert evaluate_zone(self.CFG, D("85"), None) == "attention"

    def test_boundary_30_is_neutral_low(self) -> None:
        """min=30 is inclusive → 30 falls into neutral_low, not attention_low."""
        assert evaluate_zone(self.CFG, D("30"), None) == "neutral"

    def test_boundary_70_is_neutral_high(self) -> None:
        assert evaluate_zone(self.CFG, D("70"), None) == "neutral"

    def test_none_value_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, None) is None


# ── evaluate_zone — price_vs_reference (Spec D05 §4.3) ───────────────────────


class TestEvaluateZonePriceVsReference:
    """MA200 model: reference=100, band=2% → positive if price>102, attention if <98."""

    CFG = {"model": "price_vs_reference", "neutral_band_pct": 0.02}

    def test_positive_when_price_above_band(self) -> None:
        assert evaluate_zone(self.CFG, D("100"), None, close_price=D("110")) == "positive"

    def test_attention_when_price_below_band(self) -> None:
        assert evaluate_zone(self.CFG, D("100"), None, close_price=D("90")) == "attention"

    def test_neutral_when_price_within_band(self) -> None:
        assert evaluate_zone(self.CFG, D("100"), None, close_price=D("101")) == "neutral"

    def test_exact_upper_boundary_is_positive(self) -> None:
        """price > ref*(1+band): price=102.01 → positive."""
        assert evaluate_zone(self.CFG, D("100"), None, close_price=D("102.01")) == "positive"

    def test_exact_reference_equals_neutral(self) -> None:
        """price == reference → within neutral band (|pct| = 0 ≤ 2%)."""
        assert evaluate_zone(self.CFG, D("100"), None, close_price=D("100")) == "neutral"

    def test_none_value_numeric_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, None, close_price=D("110")) is None

    def test_none_close_price_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, D("100"), None, close_price=None) is None


# ── evaluate_zone — signed_with_trend (Spec D05 §4.4) ────────────────────────


class TestEvaluateZoneSignedWithTrend:
    """MACD: near_zero_threshold=0.5. positive rising, negative falling → zones."""

    CFG = {"model": "signed_with_trend", "near_zero_threshold": 0.5}

    def test_near_zero_is_neutral(self) -> None:
        assert evaluate_zone(self.CFG, D("0.3"), None) == "neutral"

    def test_positive_and_rising_is_positive(self) -> None:
        assert evaluate_zone(
            self.CFG, D("2.0"), None, previous_value_numeric=D("1.0")
        ) == "positive"

    def test_negative_and_falling_is_attention(self) -> None:
        assert evaluate_zone(
            self.CFG, D("-2.0"), None, previous_value_numeric=D("-1.0")
        ) == "attention"

    def test_positive_but_falling_is_neutral(self) -> None:
        assert evaluate_zone(
            self.CFG, D("1.0"), None, previous_value_numeric=D("2.0")
        ) == "neutral"

    def test_negative_but_rising_is_neutral(self) -> None:
        assert evaluate_zone(
            self.CFG, D("-1.0"), None, previous_value_numeric=D("-2.0")
        ) == "neutral"

    def test_no_previous_value_is_neutral_when_positive(self) -> None:
        """Positive but no prior snapshot → can't confirm trend → neutral."""
        assert evaluate_zone(self.CFG, D("2.0"), None, previous_value_numeric=None) == "neutral"

    def test_none_value_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, None) is None


# ── evaluate_zone — categorical_state (Spec D05 §4.5) ────────────────────────


class TestEvaluateZoneCategoricalState:
    """MA50/200 cross mapping: golden_cross→positive, near_cross→neutral, death_cross→attention."""

    CFG = {
        "model": "categorical_state",
        "mapping": {
            "golden_cross": "positive",
            "near_cross":   "neutral",
            "death_cross":  "attention",
        },
    }

    def test_golden_cross_is_positive(self) -> None:
        assert evaluate_zone(self.CFG, None, "golden_cross") == "positive"

    def test_near_cross_is_neutral(self) -> None:
        assert evaluate_zone(self.CFG, None, "near_cross") == "neutral"

    def test_death_cross_is_attention(self) -> None:
        assert evaluate_zone(self.CFG, None, "death_cross") == "attention"

    def test_unknown_state_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, "unknown_state") is None

    def test_none_text_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, None) is None

    def test_analyst_sentiment_bullish_mapping(self) -> None:
        """Analyst sentiment uses same model — validate a second mapping variant."""
        cfg = {
            "model": "categorical_state",
            "mapping": {"bullish": "positive", "mixed": "neutral", "bearish": "attention"},
        }
        assert evaluate_zone(cfg, None, "bullish") == "positive"
        assert evaluate_zone(cfg, None, "mixed") == "neutral"
        assert evaluate_zone(cfg, None, "bearish") == "attention"


# ── evaluate_zone — informational_only (Spec D05 §4.6) ───────────────────────


class TestEvaluateZoneInformationalOnly:
    """Portfolio KPIs — always returns None regardless of stored value."""

    CFG = {"model": "informational_only"}

    def test_numeric_value_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, D("12.5"), None) is None

    def test_none_value_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, None) is None

    def test_text_value_returns_none(self) -> None:
        assert evaluate_zone(self.CFG, None, "anything") is None
