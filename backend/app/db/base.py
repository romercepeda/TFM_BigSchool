"""SQLAlchemy declarative base.

All ORM models inherit from Base. Alembic reads Base.metadata to detect
schema changes and generate migrations automatically.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
