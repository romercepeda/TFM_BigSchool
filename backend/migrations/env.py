"""Alembic environment configuration.

How the two drivers coexist:
- The application uses asyncpg (async) at runtime for FastAPI requests.
- Alembic uses psycopg2 (sync) for migrations — this is the standard approach
  and keeps migration scripts simple and predictable.
- The DATABASE_URL env var uses the asyncpg dialect; we swap it to psycopg2
  here so Alembic can create a synchronous connection.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import Base first, then models so their tables register on Base.metadata.
# Any new model file added to app/db/models/__init__.py is automatically picked up.
from app.db.base import Base
import app.db.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_sync_url() -> str:
    """Derive a synchronous psycopg2 URL from the asyncpg DATABASE_URL."""
    url = os.environ["DATABASE_URL"]
    return url.replace("+asyncpg", "+psycopg2")


def run_migrations_offline() -> None:
    """Generate a SQL script file without connecting to the database.

    Useful for reviewing what Alembic would execute before applying it,
    or for environments where direct DB access is restricted.
    """
    context.configure(
        url=_get_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations directly to the connected database."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_sync_url()

    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
