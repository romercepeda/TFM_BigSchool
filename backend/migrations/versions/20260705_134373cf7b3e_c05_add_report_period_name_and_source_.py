"""C05 add report_period_name and source-tracking columns to analysis_reports

Revision ID: 134373cf7b3e
Revises: 4212a57b1a97
Create Date: 2026-07-05 11:01:10.139596+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '134373cf7b3e'
down_revision: Union[str, None] = '4212a57b1a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TABLE ADD COLUMN does not auto-create the enum type the way
    # CREATE TABLE does — create both types explicitly first.
    report_date_source_enum = sa.Enum(
        'ai_extracted', 'upload_fallback', 'user_edited', 'legacy_unknown',
        name='report_date_source_enum',
    )
    report_period_name_source_enum = sa.Enum(
        'ai_extracted', 'user_edited', 'unset', name='report_period_name_source_enum',
    )
    bind = op.get_bind()
    report_date_source_enum.create(bind, checkfirst=True)
    report_period_name_source_enum.create(bind, checkfirst=True)

    # Add nullable first — existing rows need a backfill pass before either
    # source column can be made NOT NULL (Changeset C05 §4).
    op.add_column(
        'analysis_reports',
        sa.Column('report_date_source', report_date_source_enum, nullable=True),
    )
    op.add_column('analysis_reports', sa.Column('report_period_name', sa.String(length=40), nullable=True))
    op.add_column(
        'analysis_reports',
        sa.Column('report_period_name_source', report_period_name_source_enum, nullable=True),
    )

    # Backfill (C05 §4):
    #   - report_period_name / report_period_name_source: no pre-C05 row ever had
    #     a name, so every existing row is 'unset'.
    #   - report_date_source: best-effort inference — a row whose report_date
    #     equals its created_at date was (before C05) populated from the upload
    #     date fallback in disguise; everything else is undistinguishable and
    #     gets the 'legacy_unknown' value that exists only for this backfill.
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE analysis_reports SET report_period_name_source = 'unset'"
    ))
    conn.execute(sa.text(
        "UPDATE analysis_reports SET report_date_source = 'upload_fallback' "
        "WHERE report_date IS NOT NULL AND report_date = created_at::date"
    ))
    conn.execute(sa.text(
        "UPDATE analysis_reports SET report_date_source = 'legacy_unknown' "
        "WHERE report_date_source IS NULL"
    ))

    op.alter_column('analysis_reports', 'report_date_source', nullable=False)
    op.alter_column('analysis_reports', 'report_period_name_source', nullable=False)


def downgrade() -> None:
    op.drop_column('analysis_reports', 'report_period_name_source')
    op.drop_column('analysis_reports', 'report_period_name')
    op.drop_column('analysis_reports', 'report_date_source')
    op.execute('DROP TYPE IF EXISTS report_period_name_source_enum')
    op.execute('DROP TYPE IF EXISTS report_date_source_enum')
