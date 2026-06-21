"""Import all models so Alembic can discover them via Base.metadata.

Any new model file must be imported here; otherwise Alembic will not
detect its tables and will not generate migrations for them.
"""

from app.db.models.portfolio import Portfolio
from app.db.models.user import User

__all__ = ["User", "Portfolio"]
