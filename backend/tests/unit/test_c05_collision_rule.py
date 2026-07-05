"""Unit tests for the C05 §7.1 date-edit collision rule.

`plan_snapshot_retarget` is the pure decision function extracted from
`ai_report_service._retarget_report_snapshots` specifically so this critical
business logic can be tested without a database (Spec 00c coverage bar).

Fake rows are plain dataclass instances — the function under test only reads
.id, .indicator_id, and .source_ref.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest

from app.services.ai_report_service import DateCollisionError, plan_snapshot_retarget


@dataclass
class FakeSnapshot:
    id: UUID
    indicator_id: UUID
    source_ref: str | None


REPORT_ID = uuid4()
REPORT_ID_STR = str(REPORT_ID)
OTHER_REPORT_ID_STR = str(uuid4())
NEW_DATE = date(2026, 3, 31)


def _own_row(indicator_id: UUID | None = None) -> FakeSnapshot:
    return FakeSnapshot(id=uuid4(), indicator_id=indicator_id or uuid4(), source_ref=REPORT_ID_STR)


class TestNoCollision:
    def test_single_row_with_no_existing_target_moves_freely(self):
        row = _own_row()
        plan = plan_snapshot_retarget(
            [row], {}, report_id_str=REPORT_ID_STR, new_date=NEW_DATE,
        )
        assert plan == [(row, None)]

    def test_multiple_rows_none_colliding(self):
        rows = [_own_row() for _ in range(3)]
        plan = plan_snapshot_retarget(
            rows, {}, report_id_str=REPORT_ID_STR, new_date=NEW_DATE,
        )
        assert plan == [(r, None) for r in rows]


class TestSameAnalysisConsolidation:
    def test_existing_row_owned_by_same_report_consolidates(self):
        row = _own_row()
        existing = FakeSnapshot(id=uuid4(), indicator_id=row.indicator_id, source_ref=REPORT_ID_STR)
        plan = plan_snapshot_retarget(
            [row],
            {row.indicator_id: existing},
            report_id_str=REPORT_ID_STR,
            new_date=NEW_DATE,
        )
        assert plan == [(row, existing)]

    def test_existing_row_is_literally_the_same_row_is_a_no_op(self):
        # Defensive branch: if the "existing" row at the target date is the
        # very row being moved, it is not a collision and not a consolidation.
        row = _own_row()
        plan = plan_snapshot_retarget(
            [row],
            {row.indicator_id: row},
            report_id_str=REPORT_ID_STR,
            new_date=NEW_DATE,
        )
        assert plan == [(row, None)]

    def test_one_indicator_consolidates_another_moves_freely(self):
        free_row = _own_row()
        consolidating_row = _own_row()
        existing = FakeSnapshot(
            id=uuid4(), indicator_id=consolidating_row.indicator_id, source_ref=REPORT_ID_STR,
        )
        plan = plan_snapshot_retarget(
            [free_row, consolidating_row],
            {consolidating_row.indicator_id: existing},
            report_id_str=REPORT_ID_STR,
            new_date=NEW_DATE,
        )
        assert (free_row, None) in plan
        assert (consolidating_row, existing) in plan


class TestDifferentAnalysisCollision:
    def test_existing_row_from_different_report_raises(self):
        row = _own_row()
        existing = FakeSnapshot(
            id=uuid4(), indicator_id=row.indicator_id, source_ref=OTHER_REPORT_ID_STR,
        )
        with pytest.raises(DateCollisionError) as exc_info:
            plan_snapshot_retarget(
                [row], {row.indicator_id: existing}, report_id_str=REPORT_ID_STR, new_date=NEW_DATE,
            )
        assert exc_info.value.conflicting_date == NEW_DATE

    def test_existing_row_from_scheduled_job_raises(self):
        # source_ref is None for scheduled_job snapshots — never equals report_id_str.
        row = _own_row()
        existing = FakeSnapshot(id=uuid4(), indicator_id=row.indicator_id, source_ref=None)
        with pytest.raises(DateCollisionError):
            plan_snapshot_retarget(
                [row], {row.indicator_id: existing}, report_id_str=REPORT_ID_STR, new_date=NEW_DATE,
            )

    def test_one_colliding_indicator_aborts_the_whole_batch(self):
        """All-or-nothing: even if only one of several indicators collides,
        the function raises before returning any usable plan — the caller
        never applies a partial set of changes."""
        clean_row = _own_row()
        colliding_row = _own_row()
        existing = FakeSnapshot(
            id=uuid4(), indicator_id=colliding_row.indicator_id, source_ref=OTHER_REPORT_ID_STR,
        )
        with pytest.raises(DateCollisionError):
            plan_snapshot_retarget(
                [clean_row, colliding_row],
                {colliding_row.indicator_id: existing},
                report_id_str=REPORT_ID_STR,
                new_date=NEW_DATE,
            )

    def test_mixed_batch_with_consolidation_and_collision_still_aborts(self):
        consolidating_row = _own_row()
        colliding_row = _own_row()
        self_existing = FakeSnapshot(
            id=uuid4(), indicator_id=consolidating_row.indicator_id, source_ref=REPORT_ID_STR,
        )
        other_existing = FakeSnapshot(
            id=uuid4(), indicator_id=colliding_row.indicator_id, source_ref=OTHER_REPORT_ID_STR,
        )
        with pytest.raises(DateCollisionError):
            plan_snapshot_retarget(
                [consolidating_row, colliding_row],
                {
                    consolidating_row.indicator_id: self_existing,
                    colliding_row.indicator_id: other_existing,
                },
                report_id_str=REPORT_ID_STR,
                new_date=NEW_DATE,
            )


class TestEmptyInput:
    def test_no_own_rows_returns_empty_plan(self):
        plan = plan_snapshot_retarget([], {}, report_id_str=REPORT_ID_STR, new_date=NEW_DATE)
        assert plan == []
