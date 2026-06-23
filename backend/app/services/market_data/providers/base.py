"""Abstract base classes for market data and FX providers — Spec D09 §4.

Any concrete provider adapter must implement the full interface.
The data service layer depends on these interfaces, never on concrete adapters.
"""

from abc import ABC, abstractmethod
from datetime import date

from app.services.market_data.types import AssetSearchResult, FxPoint, PricePoint


class MarketDataProvider(ABC):
    """Interface for market price data (Spec D09 §4.1)."""

    @abstractmethod
    async def search_assets(self, query: str) -> list[AssetSearchResult]: ...

    @abstractmethod
    async def get_current_price(self, ticker: str) -> PricePoint: ...

    @abstractmethod
    async def get_historical_series(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PricePoint]: ...


class FxDataProvider(ABC):
    """Interface for FX rate data (Spec D09 §4.2)."""

    @abstractmethod
    async def get_current_rate(self, quote_currency: str, base_currency: str) -> FxPoint: ...

    @abstractmethod
    async def get_historical_rate(
        self, quote_currency: str, base_currency: str, on_date: date
    ) -> FxPoint: ...

    @abstractmethod
    async def is_pair_supported(self, quote_currency: str, base_currency: str) -> bool: ...
