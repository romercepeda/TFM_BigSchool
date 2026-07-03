"""Unit tests for the multi-provider cascade — Spec D12 §5, Changeset C04 §2.

Coverage target: 90%+ (Spec 00c — cascade iteration is critical business logic).
Covers: happy path, partial fallback, total failure, lookback-skip, and
heterogeneous errors across providers for the market data cascade, plus the
FX cascade's single-pair fallback and is_pair_supported behavior.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.services.market_data.cascade import (
    CascadeAssetRequest,
    FxCascadeExhaustedError,
    FxDataCascade,
    MarketCascadeExhaustedError,
    MarketDataCascade,
    merge_cascade_results,
)
from app.services.market_data.providers.base import FxDataProvider, MarketDataProvider
from app.services.market_data.types import AssetSearchResult, FxPoint, PricePoint, ProviderError

_START = date(2026, 1, 1)
_END = date(2026, 1, 5)  # 4-day range


class _FakeMarketProvider(MarketDataProvider):
    """Configurable test double: resolves listed tickers, raises for the rest."""

    def __init__(
        self,
        resolves: set[str] | None = None,
        error_kind: str = "not_found",
        max_lookback_days: int | None = None,
    ) -> None:
        self._resolves = resolves or set()
        self._error_kind = error_kind
        self.provider_max_lookback_days = max_lookback_days
        self.calls: list[str] = []

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        raise NotImplementedError

    async def get_current_price(self, ticker: str) -> PricePoint:
        self.calls.append(ticker)
        if ticker not in self._resolves:
            raise ProviderError(
                error_kind=self._error_kind, retryable=False, upstream_message="nope"
            )
        return PricePoint(as_of_date=_START, price=Decimal("1.00"), currency="")

    async def get_historical_series(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PricePoint]:
        self.calls.append(ticker)
        if ticker not in self._resolves:
            raise ProviderError(
                error_kind=self._error_kind, retryable=False, upstream_message="nope"
            )
        return [PricePoint(as_of_date=start_date, price=Decimal("1.00"), currency="")]


def _asset(ticker: str) -> CascadeAssetRequest:
    return CascadeAssetRequest(asset_id=uuid4(), ticker=ticker, market=None)


def _by_ticker(assets: list[CascadeAssetRequest], ticker: str) -> UUID:
    return next(a.asset_id for a in assets if a.ticker == ticker)


# ── Market data cascade ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_all_resolved_by_first_provider() -> None:
    assets = [_asset(f"T{i}") for i in range(10)]
    p0 = _FakeMarketProvider(resolves={a.ticker for a in assets})
    cascade = MarketDataCascade([("p0", p0)])

    result = await cascade.execute(assets, _START, _END)

    assert result.total_assets_processed == 10
    assert len(result.resolved) == 10
    assert result.resolved_by_provider == {"p0": 10}
    assert result.failures == []


@pytest.mark.asyncio
async def test_partial_fallback_across_three_providers() -> None:
    assets = [_asset(f"T{i}") for i in range(10)]
    all_tickers = {a.ticker for a in assets}
    failing = {"T0", "T1"}

    p0 = _FakeMarketProvider(resolves=all_tickers - failing)
    p1 = _FakeMarketProvider(resolves={"T0"})
    p2 = _FakeMarketProvider(resolves={"T1"})
    cascade = MarketDataCascade([("p0", p0), ("p1", p1), ("p2", p2)])

    result = await cascade.execute(assets, _START, _END)

    assert len(result.resolved) == 10
    assert result.resolved_by_provider == {"p0": 8, "p1": 1, "p2": 1}
    assert result.failures == []
    # p1 is asked about both leftovers from round 1 (resolves only T0);
    # p2 is then asked only about what's left after round 2 (T1).
    assert p1.calls == ["T0", "T1"]
    assert p2.calls == ["T1"]


@pytest.mark.asyncio
async def test_total_failure_after_exhausting_cascade() -> None:
    assets = [_asset(f"T{i}") for i in range(10)]
    all_tickers = {a.ticker for a in assets}
    failing = {"T0", "T1"}

    p0 = _FakeMarketProvider(resolves=all_tickers - failing)
    p1 = _FakeMarketProvider(resolves={"T0"})
    p2 = _FakeMarketProvider(resolves=set())  # fails T1 too
    cascade = MarketDataCascade([("p0", p0), ("p1", p1), ("p2", p2)])

    result = await cascade.execute(assets, _START, _END)

    assert len(result.resolved) == 9
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.ticker == "T1"
    assert failure.providers_tried == ["p0", "p1", "p2"]
    assert set(failure.last_error_by_provider) == {"p0", "p1", "p2"}


@pytest.mark.asyncio
async def test_provider_skipped_when_lookback_insufficient() -> None:
    assets = [_asset("T0")]
    # Required range is 4 days; this provider only covers 2 — must be
    # skipped entirely, without ever being called.
    short_lookback = _FakeMarketProvider(resolves={"T0"}, max_lookback_days=2)
    cascade = MarketDataCascade([("short", short_lookback)])

    result = await cascade.execute(assets, _START, _END)

    assert result.resolved == {}
    assert short_lookback.calls == []  # never invoked — no call consumed
    assert len(result.failures) == 1
    assert result.failures[0].reason == "insufficient_lookback"
    assert result.failures[0].providers_tried == []  # skipped, not "tried"


@pytest.mark.asyncio
async def test_heterogeneous_errors_prioritize_rate_limited_reason() -> None:
    assets = [_asset("T0")]
    p0 = _FakeMarketProvider(resolves=set(), error_kind="not_found")
    p1 = _FakeMarketProvider(resolves=set(), error_kind="rate_limited")
    cascade = MarketDataCascade([("p0", p0), ("p1", p1)])

    result = await cascade.execute(assets, _START, _END)

    assert len(result.failures) == 1
    # rate_limited outranks not_found in the reason-classification priority.
    assert result.failures[0].reason == "rate_limited"
    assert result.failures[0].providers_tried == ["p0", "p1"]


@pytest.mark.asyncio
async def test_no_cross_run_memory_every_call_restarts_at_providers_zero() -> None:
    """D12 §5.4 — a fresh cascade instance always starts at providers[0]."""
    assets = [_asset("T0")]
    p0 = _FakeMarketProvider(resolves={"T0"})
    cascade = MarketDataCascade([("p0", p0)])

    await cascade.execute(assets, _START, _END)
    await cascade.execute(assets, _START, _END)

    assert p0.calls == ["T0", "T0"]  # called again on the second run, no memoization


# ── get_current_price single-ticker fallback (post-Step-7 fix) ───────────────


@pytest.mark.asyncio
async def test_get_current_price_falls_back_to_second_provider() -> None:
    p0 = _FakeMarketProvider(resolves=set())  # rejects everything
    p1 = _FakeMarketProvider(resolves={"TEF"})
    cascade = MarketDataCascade([("p0", p0), ("p1", p1)])

    point, provider_name = await cascade.get_current_price("TEF", "BME")

    assert provider_name == "p1"
    assert point.price == Decimal("1.00")


@pytest.mark.asyncio
async def test_get_current_price_raises_when_all_providers_fail() -> None:
    p0 = _FakeMarketProvider(resolves=set())
    p1 = _FakeMarketProvider(resolves=set())
    cascade = MarketDataCascade([("p0", p0), ("p1", p1)])

    with pytest.raises(MarketCascadeExhaustedError) as exc_info:
        await cascade.get_current_price("TEF", "BME")

    assert exc_info.value.providers_tried == ["p0", "p1"]


@pytest.mark.asyncio
async def test_merge_cascade_results_combines_disjoint_runs() -> None:
    """Bootstrap-window run + incremental-window run over disjoint assets

    (Changeset C04 Step 7's per-asset lookback split) merge into one report.
    """
    bootstrap_assets = [_asset("NEW0")]
    incremental_assets = [_asset("OLD0"), _asset("OLD1")]

    p0 = _FakeMarketProvider(resolves={"NEW0"})
    bootstrap_result = await MarketDataCascade([("p0", p0)]).execute(
        bootstrap_assets, _START, _END
    )

    p1 = _FakeMarketProvider(resolves={"OLD0"})
    p2 = _FakeMarketProvider(resolves={"OLD1"})
    incremental_result = await MarketDataCascade([("p1", p1), ("p2", p2)]).execute(
        incremental_assets, _START, _END
    )

    merged = merge_cascade_results([bootstrap_result, incremental_result])

    assert merged.total_assets_processed == 3
    assert len(merged.resolved) == 3
    assert merged.resolved_by_provider == {"p0": 1, "p1": 1, "p2": 1}
    assert merged.failures == []


# ── FX data cascade ─────────────────────────────────────────────────────────────


class _FakeFxProvider(FxDataProvider):
    def __init__(self, succeeds: bool, supported: bool = True) -> None:
        self._succeeds = succeeds
        self._supported = supported
        self.calls = 0

    async def get_current_rate(self, quote_currency: str, base_currency: str) -> FxPoint:
        self.calls += 1
        if not self._succeeds:
            raise ProviderError(error_kind="network", retryable=True, upstream_message="down")
        return FxPoint(
            quote_currency=quote_currency,
            base_currency=base_currency,
            as_of_date=_START,
            rate=Decimal("1.1"),
        )

    async def get_historical_rate(
        self, quote_currency: str, base_currency: str, on_date: date
    ) -> FxPoint:
        return await self.get_current_rate(quote_currency, base_currency)

    async def is_pair_supported(self, quote_currency: str, base_currency: str) -> bool:
        return self._supported


@pytest.mark.asyncio
async def test_fx_cascade_falls_back_to_second_provider() -> None:
    p0 = _FakeFxProvider(succeeds=False)
    p1 = _FakeFxProvider(succeeds=True)
    cascade = FxDataCascade([("p0", p0), ("p1", p1)])

    point, provider_name = await cascade.get_current_rate("USD", "EUR")

    assert provider_name == "p1"
    assert point.rate == Decimal("1.1")


@pytest.mark.asyncio
async def test_fx_cascade_raises_when_exhausted() -> None:
    p0 = _FakeFxProvider(succeeds=False)
    cascade = FxDataCascade([("p0", p0)])

    with pytest.raises(FxCascadeExhaustedError) as exc_info:
        await cascade.get_current_rate("USD", "EUR")

    assert exc_info.value.providers_tried == ["p0"]


@pytest.mark.asyncio
async def test_fx_cascade_is_pair_supported_true_if_any_provider_supports() -> None:
    p0 = _FakeFxProvider(succeeds=True, supported=False)
    p1 = _FakeFxProvider(succeeds=True, supported=True)
    cascade = FxDataCascade([("p0", p0), ("p1", p1)])

    assert await cascade.is_pair_supported("USD", "EUR") is True


@pytest.mark.asyncio
async def test_fx_cascade_is_pair_supported_false_if_none_support() -> None:
    p0 = _FakeFxProvider(succeeds=True, supported=False)
    cascade = FxDataCascade([("p0", p0)])

    assert await cascade.is_pair_supported("USD", "EUR") is False
