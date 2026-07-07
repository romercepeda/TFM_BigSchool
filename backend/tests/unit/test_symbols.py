"""Unit tests for per-provider ticker qualification — Spec D12 §4/§5.

Covers the "IDR" incident (Indra Sistemas on BME silently returning
Finnhub's unrelated bare-ticker match) — Finnhub must refuse a bare ticker
on a known non-US market rather than guess.
"""

from __future__ import annotations

import pytest

from app.services.market_data.symbols import provider_symbol
from app.services.market_data.types import ProviderError


def test_already_qualified_ticker_passes_through_unchanged() -> None:
    assert provider_symbol("SAN.MC", "BME", "finnhub") == "SAN.MC"
    assert provider_symbol("TEF:BME", "BME", "twelve_data") == "TEF:BME"


def test_twelve_data_qualifies_non_us_market() -> None:
    assert provider_symbol("TEF", "BME", "twelve_data") == "TEF:BME"


def test_twelve_data_leaves_us_market_bare() -> None:
    assert provider_symbol("AAPL", "NASDAQ", "twelve_data") == "AAPL"


def test_eodhd_qualifies_via_exchange_mapping() -> None:
    assert provider_symbol("IDR", "BME", "eodhd") == "IDR.MC"


def test_finnhub_refuses_bare_ticker_on_known_non_us_market() -> None:
    """The IDR incident: Finnhub has no way to qualify a non-US ticker, so it
    must fail loud instead of silently matching an unrelated instrument."""
    with pytest.raises(ProviderError) as exc_info:
        provider_symbol("IDR", "BME", "finnhub")
    assert exc_info.value.error_kind == "api_error"
    assert exc_info.value.retryable is False


def test_finnhub_passes_through_us_market_bare_ticker() -> None:
    assert provider_symbol("AAPL", "NASDAQ", "finnhub") == "AAPL"


def test_finnhub_passes_through_unknown_market_bare_ticker() -> None:
    """Legacy assets with no market on file are passed through as-is —
    unchanged from prior behavior, since we can't tell if it's US or not."""
    assert provider_symbol("AAPL", None, "finnhub") == "AAPL"
