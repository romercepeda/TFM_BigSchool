"""Frankfurter FX provider adapter — Spec D09 §3.2.

Uses the Frankfurter API v2 (api.frankfurter.dev/v2).

FX rate convention (D04 §3.1):
    rate = units of base_currency per 1 unit of quote_currency
    Example: quote=USD, base=EUR → GET /rate/USD/EUR → rate: 0.87
    Meaning: 1 USD buys 0.87 EUR ✓

v2 endpoint used:
    GET /rate/{quote}/{base}            — current rate
    GET /rate/{quote}/{base}?date=DATE  — historical rate
    GET /currencies                     — supported currencies list
"""

import logging
from datetime import date
from decimal import Decimal

import httpx

from app.services.market_data.providers.base import FxDataProvider
from app.services.market_data.types import FxPoint, ProviderError

logger = logging.getLogger(__name__)


class FrankfurterProvider(FxDataProvider):
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._supported: set[str] | None = None

    async def _load_currencies(self) -> set[str]:
        """Lazy-load the set of supported ISO 4217 currency codes."""
        if self._supported is not None:
            return self._supported
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self._base_url}/currencies", timeout=10)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))
        data = resp.json()
        # v2 returns a list of objects with "iso_code" key.
        if isinstance(data, dict):
            self._supported = set(data.keys())
        elif isinstance(data, list):
            codes: set[str] = set()
            for item in data:
                if isinstance(item, dict):
                    code = item.get("iso_code") or item.get("isoCode") or item.get("code") or ""
                    if code:
                        codes.add(str(code))
                elif isinstance(item, str):
                    codes.add(item)
            self._supported = codes
        else:
            self._supported = set()
        return self._supported

    async def is_pair_supported(self, quote_currency: str, base_currency: str) -> bool:
        if quote_currency.upper() == base_currency.upper():
            return True
        try:
            supported = await self._load_currencies()
        except ProviderError:
            return False
        return quote_currency.upper() in supported and base_currency.upper() in supported

    async def _fetch_rate(
        self,
        quote: str,
        base: str,
        as_of_date: date | None,
    ) -> FxPoint:
        """Fetch rate from v2 /rate/{quote}/{base} endpoint."""
        if quote.upper() == base.upper():
            return FxPoint(
                quote_currency=quote.upper(),
                base_currency=base.upper(),
                as_of_date=as_of_date or date.today(),
                rate=Decimal("1"),
            )

        url = f"{self._base_url}/rate/{quote.upper()}/{base.upper()}"
        params = {"date": as_of_date.isoformat()} if as_of_date else {}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params=params, timeout=10)
            except httpx.HTTPError as exc:
                raise ProviderError(error_kind="network", retryable=True, upstream_message=str(exc))

        if resp.status_code == 404:
            raise ProviderError(
                error_kind="not_found",
                retryable=False,
                upstream_message=f"No FX data for {quote}/{base}"
                + (f" on {as_of_date}" if as_of_date else ""),
            )
        if resp.status_code in (400, 422):
            body = resp.json()
            raise ProviderError(
                error_kind="invalid_pair",
                retryable=False,
                upstream_message=body.get("message", f"Unsupported pair {quote}/{base}"),
            )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(error_kind="api_error", retryable=False, upstream_message=str(exc))

        body = resp.json()
        actual_date = date.fromisoformat(body["date"]) if "date" in body else (as_of_date or date.today())
        return FxPoint(
            quote_currency=quote.upper(),
            base_currency=base.upper(),
            as_of_date=actual_date,
            rate=Decimal(str(body["rate"])),
        )

    async def get_current_rate(self, quote_currency: str, base_currency: str) -> FxPoint:
        return await self._fetch_rate(quote_currency, base_currency, None)

    async def get_historical_rate(
        self, quote_currency: str, base_currency: str, on_date: date
    ) -> FxPoint:
        return await self._fetch_rate(quote_currency, base_currency, on_date)
