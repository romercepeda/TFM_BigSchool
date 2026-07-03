"""Persistence for CascadeResult — Spec D12 §6, Changeset C04 §3.

Separate from cascade.py so the cascade iteration logic stays free of DB
concerns (cascade.py has no SQLAlchemy imports at all).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cascade_failure import CascadeFailureEntry, CascadeFailureReport
from app.services.market_data.cascade import CascadeResult

logger = logging.getLogger(__name__)


async def persist_cascade_result(db: AsyncSession, result: CascadeResult) -> CascadeFailureReport:
    """Persist a CascadeResult as a CascadeFailureReport row.

    Persisted even when there are no failures (D12 §6.1) — an empty report
    isn't user-visible but is useful for debugging. Caller is responsible
    for the transaction commit.
    """
    report = CascadeFailureReport(
        total_assets_processed=result.total_assets_processed,
        resolved_by_provider=result.resolved_by_provider,
    )
    db.add(report)
    await db.flush()  # assign report.id before creating child rows

    for failure in result.failures:
        db.add(
            CascadeFailureEntry(
                report_id=report.id,
                asset_id=failure.asset_id,
                ticker=failure.ticker,
                reason=failure.reason,
                providers_tried=failure.providers_tried,
                last_error_by_provider=failure.last_error_by_provider,
            )
        )

    return report


async def cleanup_old_cascade_reports(db: AsyncSession, retention_days: int) -> int:
    """Hard-delete CascadeFailureReport rows older than retention_days (D12 §6.3).

    Not a Celery periodic task here — this codebase has no Celery beat
    schedule. Called from the same on-demand daily-update path that persists
    new reports, so cleanup happens naturally each time the job runs, without
    adding new scheduling infrastructure.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await db.execute(
        delete(CascadeFailureReport).where(CascadeFailureReport.run_completed_at < cutoff)
    )
    return result.rowcount or 0
