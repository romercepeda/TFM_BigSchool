"""Unit tests for the EODHD market data adapter — Spec D12 §4, Changeset C04 §1.

All HTTP calls are mocked via httpx.MockTransport (no new test dependency).
Coverage target: 90%+ (Spec 00c — cascade-adjacent provider logic).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from app.services.market_data.providers.eodhd import EODHDProvider
from app.services.market_data.providers.eodhd_ticker_mapping import to_eodhd_exchange_code
from app.services.market_data.types import ProviderError

_API_KEY = "test-key"
_BASE_URL = "https://eodhd.com/api"


def _provider(handler, daily_call_budget: int = 20) -> EODHDProvider:
    transport = httpx.MockTransport(handler)

    class _PatchedClient(httpx.AsyncClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    import app.services.market_data.providers.eodhd as eodhd_module

    eodhd_module.httpx.AsyncClient = _PatchedClient  # type: ignore[assignment]
    return EODHDProvider(base_url=_BASE_URL, api_key=_API_KEY, daily_call_budget=daily_call_budget)


@pytest.fixture(autouse=True)
def _restore_httpx_async_client():
    original = httpx.AsyncClient
    yield
    import app.services.market_data.providers.eodhd as eodhd_module

    eodhd_module.httpx.AsyncClient = original  # type: ignore[assignment]


# ── provider_max_lookback_days constant (D12 §4, C04 §1 acceptance) ──────────


def test_provider_max_lookback_days_is_365() -> None:
    assert EODHDProvider.provider_max_lookback_days == 365


# ── get_historical_series — happy path ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_historical_series_happy_path() -> None:
    body = [
        {"date": "2026-01-05", "open": 4.0, "high": 4.2, "low": 3.9, "close": 4.1,
         "adjusted_close": 4.05, "volume": 1000},
        {"date": "2026-01-02", "open": 3.9, "high": 4.0, "low": 3.8, "close": 3.95,
         "adjusted_close": 3.90, "volume": 900},
        {"date": "2026-01-06", "open": 4.1, "high": 4.3, "low": 4.0, "close": 4.2,
         "adjusted_close": 4.15, "volume": 1100},
        {"date": "2026-01-07", "open": 4.2, "high": 4.4, "low": 4.1, "close": 4.3,
         "adjusted_close": 4.25, "volume": 1200},
        {"date": "2026-01-08", "open": 4.3, "high": 4.5, "low": 4.2, "close": 4.4,
         "adjusted_close": 4.35, "volume": 1300},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/eod/SAN.MC"
        return httpx.Response(200, json=body)

    provider = _provider(handler)
    points = await provider.get_historical_series("SAN.MC", date(2026, 1, 2), date(2026, 1, 8))

    assert len(points) == 5
    assert [p.as_of_date for p in points] == sorted(p.as_of_date for p in points)
    # Uses the adjusted close, not the raw close (D12 §4).
    assert points[0].price == Decimal("3.90")
    assert points[0].volume == 900


@pytest.mark.asyncio
async def test_get_historical_series_unknown_ticker() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not found"})

    provider = _provider(handler)
    with pytest.raises(ProviderError) as exc_info:
        await provider.get_historical_series("NOPE.MC", date(2026, 1, 1), date(2026, 1, 5))

    assert exc_info.value.error_kind == "not_found"


@pytest.mark.asyncio
async def test_get_historical_series_empty_response_is_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    provider = _provider(handler)
    with pytest.raises(ProviderError) as exc_info:
        await provider.get_historical_series("SAN.MC", date(2026, 1, 1), date(2026, 1, 5))

    assert exc_info.value.error_kind == "not_found"


# ── get_current_price ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_current_price_happy_path() -> None:
    ts = int(datetime(2026, 1, 8, tzinfo=UTC).timestamp())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/real-time/SAN.MC"
        return httpx.Response(200, json={"close": 4.4, "timestamp": ts})

    provider = _provider(handler)
    point = await provider.get_current_price("SAN.MC")

    assert point.price == Decimal("4.4")
    assert point.as_of_date == date(2026, 1, 8)


# ── Rate limit — proactive, before the (budget+1)th call (D12 §4) ────────────


@pytest.mark.asyncio
async def test_rate_limit_raised_proactively_without_hitting_network() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"close": 1.0, "timestamp": None})

    provider = _provider(handler, daily_call_budget=1)

    await provider.get_current_price("SAN.MC")
    assert call_count == 1

    with pytest.raises(ProviderError) as exc_info:
        await provider.get_current_price("SAN.MC")

    assert exc_info.value.error_kind == "rate_limited"
    # The second call must never reach the network — budget already spent.
    assert call_count == 1


# ── search_assets ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_assets_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/search/santander"
        return httpx.Response(
            200,
            json=[
                {
                    "Code": "SAN",
                    "Exchange": "MC",
                    "Name": "Banco Santander SA",
                    "Type": "Common Stock",
                    "Country": "Spain",
                    "Currency": "EUR",
                }
            ],
        )

    provider = _provider(handler)
    results = await provider.search_assets("santander")

    assert len(results) == 1
    assert results[0].ticker == "SAN"
    assert results[0].market == "MC"
    assert results[0].quote_currency == "EUR"
    assert results[0].asset_type == "stock"


# ── eodhd_ticker_mapping ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("internal_market", "expected"),
    [
        ("BME", "MC"),
        ("XETR", "XETRA"),
        ("EURONEXT", "PA"),
        ("LSE", "LSE"),
        ("NASDAQ", "US"),
        ("NYSE", "US"),
        (None, "US"),
        ("bme", "MC"),  # case-insensitive
    ],
)
def test_to_eodhd_exchange_code(internal_market: str | None, expected: str) -> None:
    assert to_eodhd_exchange_code(internal_market) == expected


def test_to_eodhd_exchange_code_raises_for_unmapped_exchange() -> None:
    with pytest.raises(ProviderError) as exc_info:
        to_eodhd_exchange_code("SOME_UNKNOWN_EXCHANGE")

    assert exc_info.value.error_kind == "api_error"
