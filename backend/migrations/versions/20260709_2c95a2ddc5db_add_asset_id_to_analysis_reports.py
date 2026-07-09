"""add asset_id to analysis_reports

Revision ID: 2c95a2ddc5db
Revises: b6cb0ba24c3c
Create Date: 2026-07-09 16:15:30.737964+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c95a2ddc5db'
down_revision: Union[str, None] = 'b6cb0ba24c3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = 'fk_analysis_reports_asset_id_assets'


def upgrade() -> None:
    # Add nullable first — existing rows need a backfill pass before NOT NULL
    # can be enforced (same two-phase pattern as Changeset C05's
    # report_date_source backfill).
    op.add_column('analysis_reports', sa.Column('asset_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_analysis_reports_asset_id'), 'analysis_reports', ['asset_id'], unique=False)
    op.create_foreign_key(_FK_NAME, 'analysis_reports', 'assets', ['asset_id'], ['id'])

    # Backfill from the originating holding (Changeset C13 §2).
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE analysis_reports "
        "SET asset_id = holdings.asset_id "
        "FROM holdings "
        "WHERE analysis_reports.holding_id = holdings.id"
    ))

    op.alter_column('analysis_reports', 'asset_id', nullable=False)


def downgrade() -> None:
    op.drop_constraint(_FK_NAME, 'analysis_reports', type_='foreignkey')
    op.drop_index(op.f('ix_analysis_reports_asset_id'), table_name='analysis_reports')
    op.drop_column('analysis_reports', 'asset_id')
