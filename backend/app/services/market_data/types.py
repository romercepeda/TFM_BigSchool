"""Shared data types for the market data service — Spec D09 §4."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class AssetSearchResult:
    ticker: str
    name: str
    asset_type: Literal["stock", "etf", "fund", "crypto"]
    quote_currency: str
    market: str | None


@dataclass(frozen=True)
class PricePoint:
    as_of_date: date
    price: Decimal
    currency: str
    volume: int | None = None


@dataclass(frozen=True)
class FxPoint:
    quote_currency: str
    base_currency: str
    as_of_date: date
    rate: Decimal


class ProviderError(Exception):
    """Raised by any provider adapter when the upstream API call fails (D09 §4.3)."""

    def __init__(self, error_kind: str, retryable: bool, upstream_message: str) -> None:
        self.error_kind = error_kind
        self.retryable = retryable
        self.upstream_message = upstream_message
        super().__init__(f"ProviderError({error_kind}): {upstream_message}")
