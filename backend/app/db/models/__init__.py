"""Import all models so Alembic can discover them via Base.metadata.

Any new model file must be imported here; otherwise Alembic will not
detect its tables and will not generate migrations for them.
"""

from app.db.models.ai_report import AnalysisJob, AnalysisReport, UploadedFile
from app.db.models.asset import Asset
from app.db.models.cascade_failure import CascadeFailureEntry, CascadeFailureReport
from app.db.models.date_alert import DateAlert
from app.db.models.dividend import AssetDividendSchedule, DividendPayment
from app.db.models.holding import Holding
from app.db.models.indicator import Indicator, IndicatorSnapshot
from app.db.models.lot import Lot
from app.db.models.market_data import AssetPriceHistory, FxRateHistory
from app.db.models.portfolio import Portfolio
from app.db.models.price_level import PriceLevel, PriceLevelHistoryEntry
from app.db.models.role import Permission, Role, RolePermission, UserRole
from app.db.models.sale import Sale, SaleLotConsumption
from app.db.models.system_setting import SystemSetting
from app.db.models.user import User

__all__ = [
    "User", "Portfolio", "Asset", "Holding",
    "Lot", "Sale", "SaleLotConsumption",
    "PriceLevel", "PriceLevelHistoryEntry", "DateAlert",
    "AssetDividendSchedule", "DividendPayment",
    "AssetPriceHistory", "FxRateHistory",
    "Indicator", "IndicatorSnapshot",
    "UploadedFile", "AnalysisJob", "AnalysisReport",
    "Permission", "Role", "RolePermission", "UserRole",
    "CascadeFailureReport", "CascadeFailureEntry",
    "SystemSetting",
]
