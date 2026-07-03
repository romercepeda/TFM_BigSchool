"""Twelve Data market data provider adapter — Spec D09 §3.1."""

import logging
from datetime import date
from decimal import Decimal

import httpx

from app.services.market_data.providers.base import MarketDataProvider
from app.services.market_data.types import AssetSearchResult, PricePoint, ProviderError

logger = logging.getLogger(__name__)

_ASSET_TYPE_MAP: dict[str, str] = {
    "common stock": "stock",
    "stock": "stock",
    "etf": "etf",
    "exchange traded fund": "etf",
    "mutual fund": "fund",
    "fund": "fund",
    "digital currency": "crypto",
    "cryptocurrency": "crypto",
    "crypto": "crypto",
}


def _map_type(raw: str) -> str:
    return _ASSET_TYPE_MAP.get(raw.lower().strip(), "stock")


class TwelveDataProvider(MarketDataProvider):
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _params(self, **extra: object) -> dict:
        return {"apikey": self._api_key, **extra}

    def _raise_on_error(self, body: dict, context: str) -> None:
        code = body.get("code", 0)
        msg = body.get("message", str(body))
        retryable = code == 429
        kind = "rate_limited" if code == 429 else ("not_found" if code == 404 else "api_error")
        raise ProviderError(error_kind=kind, retryable=retryable, upstream_message=f"{context}: {msg}")

    async def search_assets(self, query: str) -> list[AssetSearchResult]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/symbol_search",
                    params=self._params(symbol=query, outputsize=20),
                    timeout=10,
                )
                body = resp.json()
                if body.get("status") == "error":
                    self._raise_on_error(body, "search_assets")
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        return [
            AssetSearchResult(
                ticker=item["symbol"].upper(),
                name=item.get("instrument_name", item["symbol"]),
                asset_type=_map_type(item.get("instrument_type", "stock")),
                quote_currency=item.get("currency", "USD").upper(),
                market=item.get("exchange"),
            )
            for item in body.get("data", [])
        ]

    async def get_current_price(self, ticker: str) -> PricePoint:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/price",
                    params=self._params(symbol=ticker),
                    timeout=10,
                )
                body = resp.json()
                if body.get("status") == "error" or "price" not in body:
                    self._raise_on_error(body, f"get_current_price({ticker})")
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        return PricePoint(
            as_of_date=date.today(),
            price=Decimal(str(body["price"])),
            currency="",
        )

    async def get_historical_series(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PricePoint]:
        if not self._api_key:
            raise ProviderError(
                error_kind="api_error",
                retryable=False,
                upstream_message="MARKET_DATA_TWELVE_DATA_API_KEY no está configurado — edita el fichero .env y reinicia el backend.",
            )
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/time_series",
                    params=self._params(
                        symbol=ticker,
                        interval="1day",
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                        outputsize=5000,
                    ),
                    timeout=30,
                )
                body = resp.json()
                if body.get("status") == "error":
                    self._raise_on_error(body, f"get_historical_series({ticker})")
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        points = [
            PricePoint(
                as_of_date=date.fromisoformat(item["datetime"][:10]),
                price=Decimal(str(item["close"])),
                currency="",
                volume=int(item["volume"]) if item.get("volume") else None,
            )
            for item in body.get("values", [])
        ]
        points.sort(key=lambda p: p.as_of_date)
        return points
