"""Multi-provider cascade — Spec D12 §5, Changeset C04 §2.

Sits between the calling code (daily job, FX resolution) and the individual
provider adapters. Iterates the ordered provider list, calling each provider
only for the subset of items the previous providers did not resolve.

Individual adapters remain provider-agnostic and know nothing about being
part of a cascade (D12 §4) — all cascade-specific logic (round-by-round
iteration, per-provider symbol qualification, lookback skipping, failure
classification) lives here.

Not wired into the market data service yet — Changeset C04 keeps this behind
the `USE_CASCADE` flag until Step 7. `CascadeResult` is a plain in-memory
result; persisting it as a `CascadeFailureReport` DB row is Changeset C04
Step 3/5, not this module's job.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.services.market_data.providers.base import FxDataProvider, MarketDataProvider
from app.services.market_data.symbols import provider_symbol
from app.services.market_data.types import FxPoint, PricePoint, ProviderError

logger = logging.getLogger(__name__)

# D12 §6.1 failure reasons, in the priority order used to pick one when an
# asset accumulated errors of more than one kind across providers. Not
# specified precisely by D12 — this cascade picks the most specific/actionable
# reason: a rate limit outranks a not-found (retrying tomorrow may resolve
# it), which outranks a generic provider error.
_REASON_PRIORITY = ("rate_limited", "not_found", "provider_error")


def _classify_reason(error_kinds: list[str]) -> str:
    for reason in _REASON_PRIORITY:
        if reason in error_kinds:
            return reason
    return "provider_error"


# ── Market data cascade ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CascadeAssetRequest:
    asset_id: UUID
    ticker: str
    market: str | None


@dataclass(frozen=True)
class CascadeAssetSuccess:
    points: list[PricePoint]
    provider: str


@dataclass(frozen=True)
class CascadeFailureEntry:
    asset_id: UUID
    ticker: str
    reason: str  # "not_found" | "rate_limited" | "insufficient_lookback" | "provider_error"
    providers_tried: list[str]
    last_error_by_provider: dict[str, str]


@dataclass(frozen=True)
class CascadeResult:
    total_assets_processed: int
    resolved: dict[UUID, CascadeAssetSuccess]
    resolved_by_provider: dict[str, int]
    failures: list[CascadeFailureEntry]


class MarketCascadeExhaustedError(ProviderError):
    """Every market data provider in the cascade failed for one ticker.

    Raised by get_current_price() below — a single-item lookup, distinct
    from execute()'s batch semantics. Subclasses ProviderError so existing
    callers that already catch it (e.g. the market-data API's 503 handler)
    need no changes.
    """

    def __init__(
        self,
        providers_tried: list[str],
        last_error_by_provider: dict[str, str],
    ) -> None:
        self.providers_tried = providers_tried
        self.last_error_by_provider = last_error_by_provider
        super().__init__(
            error_kind="provider_error",
            retryable=True,
            upstream_message=(
                f"All market data providers failed: {providers_tried}. "
                f"Errors: {last_error_by_provider}."
            ),
        )


class MarketDataCascade:
    """Iterates an ordered list of MarketDataProvider adapters (D12 §5.1)."""

    def __init__(self, providers: list[tuple[str, MarketDataProvider]]) -> None:
        self._providers = providers

    async def get_current_price(
        self, ticker: str, market: str | None
    ) -> tuple[PricePoint, str]:
        """Single-ticker current-price fallback.

        Not part of D12 §5.1's batch cascade (which only covers the daily
        job's historical series and FX rates) — added because scoping
        get_current_price out of the cascade left a visible gap: the daily
        job could maintain an asset's price *history* via a fallback
        provider while the on-demand "current price" lookup kept failing,
        hard-wired to the primary provider only.
        """
        providers_tried: list[str] = []
        last_error_by_provider: dict[str, str] = {}
        for provider_name, provider in self._providers:
            providers_tried.append(provider_name)
            symbol = provider_symbol(ticker, market, provider_name)
            try:
                point = await provider.get_current_price(symbol)
            except ProviderError as exc:
                last_error_by_provider[provider_name] = exc.upstream_message
                continue
            return point, provider_name

        logger.warning("Market data cascade exhausted for %s: tried %s.", ticker, providers_tried)
        raise MarketCascadeExhaustedError(providers_tried, last_error_by_provider)

    async def execute(
        self,
        assets: list[CascadeAssetRequest],
        start_date: date,
        end_date: date,
    ) -> CascadeResult:
        """Resolve a historical price series for every asset in `assets`.

        No cross-run memory (D12 §5.4): every call starts from providers[0].
        A provider whose `provider_max_lookback_days` is less than the
        requested range is skipped for every remaining asset without
        consuming a call (D12 §5.3) and without counting as "tried".
        """
        required_lookback_days = (end_date - start_date).days

        unresolved: dict[UUID, CascadeAssetRequest] = {a.asset_id: a for a in assets}
        resolved: dict[UUID, CascadeAssetSuccess] = {}
        resolved_by_provider: dict[str, int] = {}
        providers_tried: dict[UUID, list[str]] = {a.asset_id: [] for a in assets}
        error_kinds: dict[UUID, list[str]] = {a.asset_id: [] for a in assets}
        last_error_by_provider: dict[UUID, dict[str, str]] = {a.asset_id: {} for a in assets}

        for provider_name, provider in self._providers:
            if not unresolved:
                break

            max_lookback = provider.provider_max_lookback_days
            if max_lookback is not None and max_lookback < required_lookback_days:
                logger.info(
                    "Cascade: skipping %s for this run — max_lookback_days=%d < required=%d.",
                    provider_name, max_lookback, required_lookback_days,
                )
                continue

            for asset_id, req in list(unresolved.items()):
                providers_tried[asset_id].append(provider_name)
                symbol = provider_symbol(req.ticker, req.market, provider_name)
                try:
                    points = await provider.get_historical_series(symbol, start_date, end_date)
                except ProviderError as exc:
                    error_kinds[asset_id].append(exc.error_kind)
                    last_error_by_provider[asset_id][provider_name] = exc.upstream_message
                    continue

                resolved[asset_id] = CascadeAssetSuccess(points=points, provider=provider_name)
                resolved_by_provider[provider_name] = resolved_by_provider.get(provider_name, 0) + 1
                del unresolved[asset_id]

        failures = [
            CascadeFailureEntry(
                asset_id=asset_id,
                ticker=req.ticker,
                reason=(
                    "insufficient_lookback"
                    if not providers_tried[asset_id]
                    else _classify_reason(error_kinds[asset_id])
                ),
                providers_tried=providers_tried[asset_id],
                last_error_by_provider=last_error_by_provider[asset_id],
            )
            for asset_id, req in unresolved.items()
        ]

        return CascadeResult(
            total_assets_processed=len(assets),
            resolved=resolved,
            resolved_by_provider=resolved_by_provider,
            failures=failures,
        )


def merge_cascade_results(results: list[CascadeResult]) -> CascadeResult:
    """Combine multiple CascadeResults into one (e.g. a bootstrap-window run

    and an incremental-window run over disjoint asset subsets — D12 §5.3).
    Assumes no asset_id appears in more than one input result.
    """
    resolved: dict[UUID, CascadeAssetSuccess] = {}
    resolved_by_provider: dict[str, int] = {}
    failures: list[CascadeFailureEntry] = []
    total = 0

    for result in results:
        total += result.total_assets_processed
        resolved.update(result.resolved)
        for provider_name, count in result.resolved_by_provider.items():
            resolved_by_provider[provider_name] = resolved_by_provider.get(provider_name, 0) + count
        failures.extend(result.failures)

    return CascadeResult(
        total_assets_processed=total,
        resolved=resolved,
        resolved_by_provider=resolved_by_provider,
        failures=failures,
    )


# ── FX data cascade ─────────────────────────────────────────────────────────────


class FxCascadeExhaustedError(ProviderError):
    """Every FX provider in the cascade failed for one pair (D12 §5.2).

    Subclasses ProviderError so existing callers that already catch
    ProviderError (e.g. the market-data API's 503 handler) need no changes.
    """

    def __init__(
        self,
        providers_tried: list[str],
        last_error_by_provider: dict[str, str],
    ) -> None:
        self.providers_tried = providers_tried
        self.last_error_by_provider = last_error_by_provider
        super().__init__(
            error_kind="provider_error",
            retryable=True,
            upstream_message=(
                f"All FX providers failed: {providers_tried}. Errors: {last_error_by_provider}."
            ),
        )


class FxDataCascade:
    """Iterates an ordered list of FxDataProvider adapters (D12 §5.2).

    FX calls are single-pair, not batch, so this cascades one call at a time
    rather than round-by-round over a set of items. With v1's single-element
    `fx_data.providers` list this degenerates to today's single-provider
    behavior, exactly as D12 §5.2 specifies.
    """

    def __init__(self, providers: list[tuple[str, FxDataProvider]]) -> None:
        self._providers = providers

    async def _try_each(
        self, call_name: str, invoke: Callable[[FxDataProvider], Awaitable[FxPoint]]
    ) -> tuple[FxPoint, str]:
        providers_tried: list[str] = []
        last_error_by_provider: dict[str, str] = {}
        for provider_name, provider in self._providers:
            providers_tried.append(provider_name)
            try:
                point = await invoke(provider)
            except ProviderError as exc:
                last_error_by_provider[provider_name] = exc.upstream_message
                continue
            return point, provider_name

        logger.warning("FX cascade exhausted for %s: tried %s.", call_name, providers_tried)
        raise FxCascadeExhaustedError(providers_tried, last_error_by_provider)

    async def get_current_rate(
        self, quote_currency: str, base_currency: str
    ) -> tuple[FxPoint, str]:
        return await self._try_each(
            "get_current_rate",
            lambda p: p.get_current_rate(quote_currency, base_currency),
        )

    async def get_historical_rate(
        self, quote_currency: str, base_currency: str, on_date: date
    ) -> tuple[FxPoint, str]:
        return await self._try_each(
            "get_historical_rate",
            lambda p: p.get_historical_rate(quote_currency, base_currency, on_date),
        )

    async def is_pair_supported(self, quote_currency: str, base_currency: str) -> bool:
        """True if any provider in the cascade supports the pair.

        Unlike search (D12 §5.5), this is a capability check, not a data
        fetch that ties the asset to one provider's identifier convention —
        so consulting every provider in the list is safe and desirable.
        """
        for _, provider in self._providers:
            try:
                if await provider.is_pair_supported(quote_currency, base_currency):
                    return True
            except ProviderError as exc:
                logger.warning(
                    "is_pair_supported check failed for %s/%s: %s",
                    quote_currency, base_currency, exc,
                )
        return False
