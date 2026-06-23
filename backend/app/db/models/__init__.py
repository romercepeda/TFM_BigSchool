"""Import all models so Alembic can discover them via Base.metadata.

Any new model file must be imported here; otherwise Alembic will not
detect its tables and will not generate migrations for them.
"""

from app.db.models.asset import Asset
from app.db.models.holding import Holding
from app.db.models.indicator import Indicator, IndicatorSnapshot
from app.db.models.lot import Lot
from app.db.models.market_data import AssetPriceHistory, FxRateHistory
from app.db.models.portfolio import Portfolio
from app.db.models.price_level import PriceLevel, PriceLevelHistoryEntry
from app.db.models.sale import Sale, SaleLotConsumption
from app.db.models.user import User

__all__ = [
    "User", "Portfolio", "Asset", "Holding",
    "Lot", "Sale", "SaleLotConsumption",
    "PriceLevel", "PriceLevelHistoryEntry",
    "AssetPriceHistory", "FxRateHistory",
    "Indicator", "IndicatorSnapshot",
]
