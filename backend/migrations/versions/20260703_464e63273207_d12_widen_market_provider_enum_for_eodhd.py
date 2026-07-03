"""d12 widen market provider enum for eodhd

Revision ID: 464e63273207
Revises: d8b2945bc077
Create Date: 2026-07-03 16:18:43.019801+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '464e63273207'
down_revision: Union[str, None] = 'd8b2945bc077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate does not detect enum member additions for an existing
    # Postgres type, so this is hand-written (Spec D12 §8, Changeset C04
    # Step 7 — the cascade can now persist provider='eodhd' rows).
    op.execute("ALTER TYPE market_provider_enum ADD VALUE IF NOT EXISTS 'eodhd'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Removing 'eodhd' cleanly
    # would require recreating the enum type and rewriting every dependent
    # column, which isn't worth it for a value this migration only adds
    # (never removes existing data). Left as a no-op; not reversible.
    pass
