"""Unit tests for report date/name resolution — Changeset C05 §5.

Tests cover the pure functions used by the analysis worker to decide the
IndicatorSnapshot as_of_date and its provenance. No DB, no external calls.
"""

from __future__ import annotations

from datetime import date

from app.worker.tasks import _resolve_report_date, _resolve_report_period_name

_TODAY = date(2026, 7, 5)


class TestResolveReportDate:
    def test_valid_past_date_is_used_as_extracted(self):
        resolved, source = _resolve_report_date("2026-03-31", today=_TODAY, job_id="j1")
        assert resolved == date(2026, 3, 31)
        assert source == "ai_extracted"

    def test_valid_date_equal_to_today_is_used_as_extracted(self):
        resolved, source = _resolve_report_date("2026-07-05", today=_TODAY, job_id="j1")
        assert resolved == _TODAY
        assert source == "ai_extracted"

    def test_null_date_falls_back_to_today(self):
        resolved, source = _resolve_report_date(None, today=_TODAY, job_id="j1")
        assert resolved == _TODAY
        assert source == "upload_fallback"

    def test_empty_string_falls_back_to_today(self):
        resolved, source = _resolve_report_date("", today=_TODAY, job_id="j1")
        assert resolved == _TODAY
        assert source == "upload_fallback"

    def test_unparsable_date_falls_back_to_today(self):
        resolved, source = _resolve_report_date("not-a-date", today=_TODAY, job_id="j1")
        assert resolved == _TODAY
        assert source == "upload_fallback"

    def test_future_date_is_treated_as_null_safety_check(self):
        resolved, source = _resolve_report_date("2026-12-31", today=_TODAY, job_id="j1")
        assert resolved == _TODAY
        assert source == "upload_fallback"


class TestResolveReportPeriodName:
    def test_present_name_is_returned(self):
        assert _resolve_report_period_name("Q1 2026") == "Q1 2026"

    def test_none_returns_none(self):
        assert _resolve_report_period_name(None) is None

    def test_empty_string_returns_none(self):
        assert _resolve_report_period_name("") is None

    def test_whitespace_only_returns_none(self):
        assert _resolve_report_period_name("   ") is None

    def test_name_is_stripped(self):
        assert _resolve_report_period_name("  Q1 2026  ") == "Q1 2026"

    def test_overlong_name_is_truncated_to_column_length(self):
        long_name = "A" * 60
        result = _resolve_report_period_name(long_name)
        assert result is not None
        assert len(result) == 40
        assert result == "A" * 40
