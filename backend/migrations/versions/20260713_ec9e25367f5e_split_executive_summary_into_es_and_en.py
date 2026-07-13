"""split executive_summary into es and en

Revision ID: ec9e25367f5e
Revises: 1b95e4b4656c
Create Date: 2026-07-13 12:30:06.975093+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec9e25367f5e'
down_revision: Union[str, None] = '1b95e4b4656c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Manually adjusted (Changeset C18 §3.1): existing reports have only one
    # summary, in whatever language they happened to be generated in. There is
    # no reliable way to retroactively translate them without a new AI call per
    # row, so both new columns are backfilled with the *same* pre-existing text
    # — a known, accepted data-quality gap for pre-changeset reports only. New
    # analyses (post-changeset) always populate both columns with genuinely
    # distinct ES/EN text via the worker.
    op.add_column('analysis_reports', sa.Column('executive_summary_es', sa.Text(), nullable=True))
    op.add_column('analysis_reports', sa.Column('executive_summary_en', sa.Text(), nullable=True))

    analysis_reports = sa.table(
        'analysis_reports',
        sa.column('executive_summary', sa.Text()),
        sa.column('executive_summary_es', sa.Text()),
        sa.column('executive_summary_en', sa.Text()),
    )
    op.execute(
        analysis_reports.update().values(
            executive_summary_es=analysis_reports.c.executive_summary,
            executive_summary_en=analysis_reports.c.executive_summary,
        )
    )

    op.alter_column('analysis_reports', 'executive_summary_es', nullable=False)
    op.alter_column('analysis_reports', 'executive_summary_en', nullable=False)
    op.drop_column('analysis_reports', 'executive_summary')


def downgrade() -> None:
    # Reverse backfill: the ES column is chosen arbitrarily as the source for
    # the merged single-language column since both were byte-identical for any
    # pre-changeset row, and downgrading loses the bilingual split anyway.
    op.add_column('analysis_reports', sa.Column('executive_summary', sa.TEXT(), autoincrement=False, nullable=True))

    analysis_reports = sa.table(
        'analysis_reports',
        sa.column('executive_summary', sa.Text()),
        sa.column('executive_summary_es', sa.Text()),
    )
    op.execute(
        analysis_reports.update().values(executive_summary=analysis_reports.c.executive_summary_es)
    )

    op.alter_column('analysis_reports', 'executive_summary', nullable=False)
    op.drop_column('analysis_reports', 'executive_summary_en')
    op.drop_column('analysis_reports', 'executive_summary_es')
