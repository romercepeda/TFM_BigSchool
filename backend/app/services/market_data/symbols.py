"""Per-provider ticker qualification for the cascade layer — Spec D12 §4/§5.

Used by cascade.py to build the symbol each provider's adapter expects from
an asset's internal (ticker, market) pair. The pre-cascade single-provider
path in service.py has its own separate `_provider_symbol()` — the two are
not unified until Changeset C04 Step 7 retires the legacy path, so the live
path is never touched mid-migration.
"""

from app.services.market_data.providers.eodhd_ticker_mapping import (
    US_EXCHANGES,
    to_eodhd_exchange_code,
)
from app.services.market_data.types import ProviderError


def provider_symbol(ticker: str, market: str | None, provider: str) -> str:
    """Build the exchange-qualified symbol for the given provider.

    Twelve Data — non-US format: TICKER:MARKET (e.g. TEF:BME).
    EODHD — non-US format: TICKER.SUFFIX (e.g. SAN.MC), via eodhd_ticker_mapping.
    Finnhub — no bare-ticker qualification convention of its own; its /search
    results already return fully-qualified symbols, which the ':'/'.'
    passthrough below already handles. For a bare ticker on a *known* non-US
    market, refuse rather than send the unqualified ticker: Finnhub's catalog
    is US-centric, so a bare foreign ticker can silently match an unrelated
    instrument (e.g. "IDR" — Indra Sistemas on BME — matching Finnhub's own
    listing for the Indonesian Rupiah instead, per the incident that added
    this guard).

    If the ticker already contains ':' or '.' it is assumed to be fully
    qualified and is returned as-is regardless of provider.
    """
    if ":" in ticker or "." in ticker:
        return ticker

    if provider == "twelve_data":
        if market and market.upper() not in US_EXCHANGES:
            return f"{ticker}:{market}"
        return ticker

    if provider == "eodhd":
        return f"{ticker}.{to_eodhd_exchange_code(market)}"

    if provider == "finnhub":
        if market and market.upper() not in US_EXCHANGES:
            raise ProviderError(
                error_kind="api_error",
                retryable=False,
                upstream_message=(
                    f"Finnhub has no exchange-qualification convention for "
                    f"non-US tickers; refusing to guess a symbol for "
                    f"{ticker!r} on market {market!r} rather than risk "
                    f"matching an unrelated instrument."
                ),
            )
        return ticker

    return ticker
