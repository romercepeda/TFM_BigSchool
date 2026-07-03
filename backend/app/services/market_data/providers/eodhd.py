"""EODHD market data provider adapter — Spec D12 §4.

Chosen because its free tier confirms European exchange coverage (BME, Xetra,
Euronext, LSE) that Twelve Data's free tier and Finnhub's free tier do not
together provide reliably (Spec D12 §3, Changeset C03).

Callers are expected to pass an already exchange-qualified ticker (the same
convention TwelveDataProvider and FinnhubProvider follow) — e.g. "SAN.MC".
Building that qualified symbol from an internal ticker + market code is the
job of `eodhd_ticker_mapping.to_eodhd_exchange_code()`, called by the market
data service once the cascade layer (Changeset C04 §2) wires this adapter in.

Quirks normalized here (D12 §4):
- Dates are returned as "YYYY-MM-DD" strings.
- Historical series exposes both a raw and a split/dividend-adjusted close;
  this adapter always uses the adjusted close, for consistency with what
  Twelve Data returns.
- Free tier: 1 year of historical depth (`provider_max_lookback_days`) and a
  tight daily call budget, tracked in-memory and enforced proactively so the
  cascade layer never wastes the adapter's last calls on a call that would
  be rejected anyway.
"""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from app.services.market_data.providers.base import MarketDataProvider
from app.services.market_data.types import AssetSearchResult, PricePoint, ProviderError

logger = logging.getLogger(__name__)

_ASSET_TYPE_MAP: dict[str, str] = {
    "common stock": "stock",
    "stock": "stock",
    "etf": "etf",
    "fund": "fund",
    "mutual fund": "fund",
    "preferred stock": "stock",
}


def _map_type(raw: str) -> str:
    return _ASSET_TYPE_MAP.get(raw.lower().strip(), "stock")


class EODHDProvider(MarketDataProvider):
    """Adapter for the EODHD API. Read-only fallback provider (D12 §3)."""

    # Free tier historical depth — read by the cascade layer to skip this
    # provider (without consuming a call) when a request needs deeper
    # history than EODHD can serve (D12 §5.3).
    provider_max_lookback_days: int = 365

    def __init__(self, base_url: str, api_key: str, daily_call_budget: int = 20) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._daily_call_budget = daily_call_budget
        self._calls_today = 0
        self._counter_date: date = datetime.now(UTC).date()

    # ── Proactive rate-limit tracking (D12 §4) ────────────────────────────────

    def _reserve_call(self) -> None:
        """Consume one call from today's budget, raising before the (budget+1)th.

        Resets at UTC midnight. Raises ProviderError(error_kind="rate_limited")
        *before* making the request, so the last remaining calls are never
        spent on a call that the cascade layer would just retry elsewhere.
        """
        today = datetime.now(UTC).date()
        if today != self._counter_date:
            self._counter_date = today
            self._calls_today = 0

        if self._calls_today >= self._daily_call_budget:
            raise ProviderError(
                error_kind="rate_limited",
                retryable=False,
                upstream_message=(
                    f"EODHD daily call budget ({self._daily_call_budget}) already "
                    f"consumed for {today.isoformat()}."
                ),
            )
        self._calls_today += 1

    def _params(self, **extra: object) -> dict:
        return {"api_token": self._api_key, "fmt": "json", **extra}

    def _raise_for_response(self, resp: httpx.Response, context: str) -> None:
        if resp.status_code in (401, 403):
            raise ProviderError(
                error_kind="api_error",
                retryable=False,
                upstream_message=(
                    f"{context}: EODHD rejected the API key (HTTP {resp.status_code})."
                ),
            )
        if resp.status_code == 404:
            raise ProviderError(
                error_kind="not_found",
                retryable=False,
                upstream_message=f"{context}: symbol not found (HTTP 404).",
            )
        if resp.status_code == 429:
            raise ProviderError(
                error_kind="rate_limited",
                retryable=True,
                upstream_message=f"{context}: EODHD returned HTTP 429.",
            )
        resp.raise_for_status()

    # ── MarketDataProvider interface ──────────────────────────────────────────

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        self._reserve_call()
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/search/{query}",
                    params=self._params(),
                    timeout=10,
                )
                self._raise_for_response(resp, "search_assets")
            except httpx.HTTPError as exc:
                raise ProviderError(
                    error_kind="network", retryable=True, upstream_message=str(exc)
                ) from exc

        body = resp.json()
        return [
            AssetSearchResult(
                ticker=item["Code"].upper(),
                name=item.get("Name", item["Code"]),
                asset_type=_map_type(item.get("Type", "stock")),
                quote_currency=item.get("Currency", "USD").upper(),
                market=item.get("Exchange"),
            )
            for item in body
        ]

    async def get_current_price(self, ticker: str) -> PricePoint:
        self._reserve_call()
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/real-time/{ticker}",
                    params=self._params(),
                    timeout=10,
                )
                self._raise_for_response(resp, f"get_current_price({ticker})")
            except httpx.HTTPError as exc:
                raise ProviderError(
                    error_kind="network", retryable=True, upstream_message=str(exc)
                ) from exc

        body = resp.json()
        close = body.get("close")
        if close is None or body.get("code") == "NA":
            raise ProviderError(
                error_kind="not_found",
                retryable=False,
                upstream_message=f"get_current_price({ticker}): no current price in response.",
            )

        ts = body.get("timestamp")
        as_of = datetime.fromtimestamp(ts, tz=UTC).date() if ts else date.today()
        return PricePoint(as_of_date=as_of, price=Decimal(str(close)), currency="")

    async def get_historical_series(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PricePoint]:
        self._reserve_call()
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/eod/{ticker}",
                    params={
                        "api_token": self._api_key,
                        "fmt": "json",
                        "from": start_date.isoformat(),
                        "to": end_date.isoformat(),
                        "period": "d",
                    },
                    timeout=30,
                )
                self._raise_for_response(resp, f"get_historical_series({ticker})")
            except httpx.HTTPError as exc:
                raise ProviderError(
                    error_kind="network", retryable=True, upstream_message=str(exc)
                ) from exc

        body = resp.json()
        if not body:
            raise ProviderError(
                error_kind="not_found",
                retryable=False,
                upstream_message=f"get_historical_series({ticker}): empty series in range.",
            )

        points = [
            PricePoint(
                as_of_date=date.fromisoformat(item["date"]),
                price=Decimal(str(item["adjusted_close"])),
                currency="",
                volume=int(item["volume"]) if item.get("volume") else None,
            )
            for item in body
        ]
        points.sort(key=lambda p: p.as_of_date)
        return points
