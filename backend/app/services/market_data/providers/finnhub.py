"""Finnhub market data provider adapter — Spec D09 §3.1."""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

from app.services.market_data.providers.base import MarketDataProvider
from app.services.market_data.types import AssetSearchResult, PricePoint, ProviderError

logger = logging.getLogger(__name__)

_ASSET_TYPE_MAP: dict[str, str] = {
    "common stock": "stock",
    "stock": "stock",
    "etp": "etf",
    "etf": "etf",
    "mutual fund": "fund",
    "fund": "fund",
    "crypto": "crypto",
    "cryptocurrency": "crypto",
}


def _map_type(raw: str) -> str:
    return _ASSET_TYPE_MAP.get(raw.lower().strip(), "stock")


def _to_unix(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


class FinnhubProvider(MarketDataProvider):
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict:
        return {"X-Finnhub-Token": self._api_key}

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/search",
                    params={"q": query},
                    headers=self._headers(),
                    timeout=10,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        body = resp.json()
        if "error" in body:
            raise ProviderError(error_kind="api_error", retryable=False, upstream_message=body["error"])

        return [
            AssetSearchResult(
                ticker=item.get("displaySymbol", item.get("symbol", "")).upper(),
                name=item.get("description", item.get("symbol", "")),
                asset_type=_map_type(item.get("type", "stock")),
                quote_currency="USD",
                market=None,
            )
            for item in body.get("result", [])
        ]

    async def get_current_price(self, ticker: str) -> PricePoint:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/quote",
                    params={"symbol": ticker},
                    headers=self._headers(),
                    timeout=10,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        body = resp.json()
        if "error" in body:
            raise ProviderError(error_kind="api_error", retryable=False, upstream_message=body["error"])

        current_price = body.get("c", 0)
        if not current_price:
            raise ProviderError(
                error_kind="not_found",
                retryable=False,
                upstream_message=f"No current price for {ticker} (received 0)",
            )

        ts = body.get("t", 0)
        as_of = datetime.fromtimestamp(ts, tz=timezone.utc).date() if ts else date.today()

        return PricePoint(as_of_date=as_of, price=Decimal(str(current_price)), currency="")

    async def get_historical_series(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PricePoint]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/stock/candle",
                    params={
                        "symbol": ticker,
                        "resolution": "D",
                        "from": _to_unix(start_date),
                        "to": _to_unix(end_date),
                    },
                    headers=self._headers(),
                    timeout=30,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        body = resp.json()
        if body.get("s") != "ok":
            msg = body.get("error", f"unexpected status: {body.get('s', 'unknown')}")
            kind = "not_found" if body.get("s") == "no_data" else "api_error"
            raise ProviderError(error_kind=kind, retryable=False, upstream_message=msg)

        points = [
            PricePoint(
                as_of_date=datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                price=Decimal(str(close)),
                currency="",
            )
            for ts, close in zip(body.get("t", []), body.get("c", []))
        ]
        points.sort(key=lambda p: p.as_of_date)
        return points
