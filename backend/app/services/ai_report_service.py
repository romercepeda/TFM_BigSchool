"""AI Report Analysis service layer — Spec D07.

Responsibilities:
  - PDF validation (content sniffing + size check)
  - UploadedFile + AnalysisJob creation, Celery task enqueue
  - Query helpers: reports for a holding, single report, pending jobs
  - Delete report (cascade to job, uploaded file, indicator snapshots)
  - Load prompt template and extraction schema (cached at module level)
  - fetch_system_context: gather available system data to enrich the AI prompt
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_report import AnalysisJob, AnalysisReport, UploadedFile
from app.db.models.indicator import Indicator, IndicatorSnapshot
from app.db.models.market_data import AssetPriceHistory

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent.parent / "ai_extraction_prompt.md"
_SCHEMA_PATH = Path(__file__).parent.parent.parent / "ai_extraction_schema.json"

_PDF_MAGIC = b"%PDF-"

# ── File-level caches (loaded once at first call) ─────────────────────────────
_prompt_cache: str | None = None
_schema_cache: dict | None = None


def load_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        if not _PROMPT_PATH.exists():
            raise RuntimeError(f"ai_extraction_prompt.md not found at {_PROMPT_PATH}")
        _prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


def load_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        if not _SCHEMA_PATH.exists():
            raise RuntimeError(f"ai_extraction_schema.json not found at {_SCHEMA_PATH}")
        _schema_cache = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema_cache


# ── System context fetch (enriches the AI prompt with DB data) ────────────────

#: Qualitative metrics are excluded from historical context (not useful for computation).
_SKIP_CONTEXT_KEYS = {"analyst_sentiment"}

#: Maximum number of prior snapshots returned per metric key.
_MAX_HISTORY_PER_KEY = 4


async def fetch_system_context(
    asset_id: UUID,
    quote_currency: str,
    db: AsyncSession,
) -> dict:
    """Return a dict of system-available data for an asset to enrich the AI prompt.

    Each data source is fetched independently and failures are silently swallowed
    so that a missing source never aborts the analysis.

    Returns an empty dict when nothing is available (caller treats it as no context).

    Keys returned (all optional):
        current_price    — float, latest close price
        price_as_of      — ISO date string of latest price row
        quote_currency   — currency code (e.g. "USD")
        historical_indicators — list of {metric, value, as_of} dicts, at most
                                 _MAX_HISTORY_PER_KEY entries per metric key
    """
    ctx: dict = {}

    # ── Latest close price ────────────────────────────────────────────────────
    try:
        price_row = await db.scalar(
            select(AssetPriceHistory)
            .where(AssetPriceHistory.asset_id == asset_id)
            .order_by(AssetPriceHistory.as_of_date.desc())
            .limit(1)
        )
        if price_row is not None:
            ctx["current_price"] = float(price_row.close_price)
            ctx["price_as_of"] = price_row.as_of_date.isoformat()
            ctx["quote_currency"] = quote_currency
            logger.debug(
                "System context [%s]: current_price=%.4f as_of=%s",
                asset_id, price_row.close_price, price_row.as_of_date,
            )
    except Exception as exc:
        logger.debug("System context [%s]: price fetch failed — %s", asset_id, exc)

    # ── Prior AI-derived indicator snapshots ──────────────────────────────────
    try:
        rows = (await db.execute(
            select(
                IndicatorSnapshot.as_of_date,
                IndicatorSnapshot.value_numeric,
                Indicator.ai_extraction_key,
            )
            .join(Indicator, Indicator.id == IndicatorSnapshot.indicator_id)
            .where(
                IndicatorSnapshot.subject_type == "asset",
                IndicatorSnapshot.subject_id == asset_id,
                IndicatorSnapshot.source == "ai_analysis",
                Indicator.ai_extraction_key.isnot(None),
                IndicatorSnapshot.value_numeric.isnot(None),
            )
            .order_by(IndicatorSnapshot.as_of_date.desc())
            .limit(20)
        )).all()

        seen: dict[str, int] = {}
        history = []
        for as_of_date, value_numeric, key in rows:
            if key in _SKIP_CONTEXT_KEYS:
                continue
            count = seen.get(key, 0)
            if count >= _MAX_HISTORY_PER_KEY:
                continue
            history.append({
                "metric": key,
                "value": float(value_numeric),
                "as_of": as_of_date.isoformat(),
            })
            seen[key] = count + 1

        if history:
            ctx["historical_indicators"] = history
            logger.debug(
                "System context [%s]: %d historical indicator entries injected.",
                asset_id, len(history),
            )
    except Exception as exc:
        logger.debug("System context [%s]: indicator fetch failed — %s", asset_id, exc)

    logger.debug("System context [%s]: final keys=%s", asset_id, list(ctx.keys()))
    return ctx


# ── PDF validation ────────────────────────────────────────────────────────────


def validate_pdf(content: bytes, filename: str, max_size_mb: int) -> None:
    """Raise ValueError if the file is not a valid PDF or exceeds the size limit.

    Validation by content sniffing, not extension (Spec 00b §4).
    """
    max_bytes = max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(
            f"File exceeds the {max_size_mb} MB limit "
            f"({len(content) / 1024 / 1024:.1f} MB uploaded)."
        )
    if not content[:5] == _PDF_MAGIC:
        raise ValueError(
            f"File '{filename}' is not a valid PDF (content sniff failed)."
        )


# ── Upload + enqueue ──────────────────────────────────────────────────────────


async def create_upload_and_job(
    db: AsyncSession,
    user_id: UUID,
    holding_id: UUID,
    content: bytes,
    filename: str,
    mime_type: str,
) -> AnalysisJob:
    """Persist UploadedFile + AnalysisJob and enqueue the Celery task.

    Returns the newly created AnalysisJob (status=queued).
    The caller must call await db.commit() after this function returns.
    """
    uploaded_file = UploadedFile(
        user_id=user_id,
        holding_id=holding_id,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        content=content,
    )
    db.add(uploaded_file)
    await db.flush()  # assign uploaded_file.id

    job = AnalysisJob(
        holding_id=holding_id,
        uploaded_file_id=uploaded_file.id,
        status="queued",
        attempt_count=0,
    )
    db.add(job)
    await db.flush()  # assign job.id

    # Commit before enqueueing so the worker can load the job from DB
    await db.commit()

    # Enqueue Celery task — import here to avoid circular import at module load
    from app.worker.tasks import analyze_report_task
    try:
        analyze_report_task.delay(str(job.id))
    except Exception as exc:
        # The job row is already committed as "queued" — if enqueueing itself
        # fails (e.g. broker unreachable), it would otherwise sit orphaned in
        # "queued" forever, since no worker will ever pick it up. Mark it
        # failed so it doesn't get stuck in the pending-jobs count (D07 §7).
        job.status = "failed"
        job.last_error = f"Failed to enqueue analysis task: {exc}"[:500]
        job.completed_at = datetime.now(UTC)
        await db.commit()
        logger.error("Failed to enqueue analyze_report_task for job %s: %s", job.id, exc)
        raise

    logger.info("Enqueued analyze_report_task for job %s (holding %s).", job.id, holding_id)

    return job


# ── Query helpers ─────────────────────────────────────────────────────────────


async def get_reports_for_holding(
    db: AsyncSession,
    holding_id: UUID,
) -> list[AnalysisReport]:
    """Return all AnalysisReports for a holding, sorted by report_date desc."""
    result = await db.execute(
        select(AnalysisReport)
        .where(AnalysisReport.holding_id == holding_id)
        .order_by(
            AnalysisReport.report_date.desc().nulls_last(),
            AnalysisReport.created_at.desc(),
        )
    )
    return list(result.scalars().all())


async def get_report(
    db: AsyncSession,
    report_id: UUID,
    user_id: UUID,
) -> AnalysisReport | None:
    """Return a report if it belongs to the given user (via UploadedFile.user_id)."""
    result = await db.execute(
        select(AnalysisReport)
        .join(UploadedFile, UploadedFile.id == AnalysisReport.uploaded_file_id)
        .where(
            AnalysisReport.id == report_id,
            UploadedFile.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_job(
    db: AsyncSession,
    job_id: UUID,
    user_id: UUID,
) -> AnalysisJob | None:
    """Return a job if it belongs to the given user (via UploadedFile.user_id)."""
    result = await db.execute(
        select(AnalysisJob)
        .join(UploadedFile, UploadedFile.id == AnalysisJob.uploaded_file_id)
        .where(
            AnalysisJob.id == job_id,
            UploadedFile.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_jobs_for_user(
    db: AsyncSession,
    user_id: UUID,
    statuses: list[str] | None = None,
    limit: int = 50,
) -> list[AnalysisJob]:
    """Return recent jobs for a user, optionally filtered by status."""
    q = (
        select(AnalysisJob)
        .join(UploadedFile, UploadedFile.id == AnalysisJob.uploaded_file_id)
        .where(UploadedFile.user_id == user_id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(limit)
    )
    if statuses:
        q = q.where(AnalysisJob.status.in_(statuses))
    result = await db.execute(q)
    return list(result.scalars().all())


# ── Update report metadata (Changeset C05 §7) ─────────────────────────────────


class DateCollisionError(Exception):
    """Raised when a report-date edit collides with another analysis's
    snapshot for the same (indicator, subject, date) — C05 §7.1."""

    def __init__(self, conflicting_date):
        self.conflicting_date = conflicting_date
        super().__init__(f"Another analysis already has a report dated {conflicting_date}.")


async def update_report_metadata(
    db: AsyncSession,
    report: AnalysisReport,
    *,
    new_report_date=None,
    new_report_period_name: str | None = None,
) -> AnalysisReport:
    """Atomically update report_date/report_period_name and derived snapshots.

    Only fields explicitly provided (non-None) are changed. Raises
    DateCollisionError — with nothing written — if the new date collides
    with a snapshot from a *different* analysis (C05 §7.1); the caller maps
    this to HTTP 409.
    """
    if new_report_date is not None and new_report_date != report.report_date:
        await _retarget_report_snapshots(db, report, new_report_date)
        report.report_date = new_report_date
        report.report_date_source = "user_edited"

    if new_report_period_name is not None and new_report_period_name != report.report_period_name:
        report.report_period_name = new_report_period_name
        report.report_period_name_source = "user_edited"

    await db.flush()
    return report


def plan_snapshot_retarget(
    own_rows: list[IndicatorSnapshot],
    existing_by_indicator: dict,
    *,
    report_id_str: str,
    new_date,
) -> list[tuple[IndicatorSnapshot, IndicatorSnapshot | None]]:
    """Pure C05 §7.1 collision decision — no DB access, fully unit-testable.

    Args:
        own_rows: this report's own IndicatorSnapshot rows (any current date).
        existing_by_indicator: {indicator_id: row-or-None} — whatever already
            occupies `new_date` for that indicator, if anything.
        report_id_str: str(report.id), to recognize "this same analysis".
        new_date: the date being moved to (only used for the error message).

    Returns:
        [(row, consolidate_target_or_None), ...] where consolidate_target is
        set when `row` must be deleted and its values merged onto an existing
        row already at new_date owned by this same report (self-collision).

    Raises:
        DateCollisionError: an indicator's target date is held by a
            *different* analysis. Nothing has been mutated at this point —
            the caller applies the plan only after this returns cleanly.
    """
    plan: list[tuple[IndicatorSnapshot, IndicatorSnapshot | None]] = []
    for row in own_rows:
        existing = existing_by_indicator.get(row.indicator_id)

        if existing is not None and existing.id != row.id and existing.source_ref != report_id_str:
            raise DateCollisionError(new_date)

        other_self_row = existing if (existing is not None and existing.id != row.id) else None
        plan.append((row, other_self_row))
    return plan


async def _retarget_report_snapshots(
    db: AsyncSession,
    report: AnalysisReport,
    new_date,
) -> None:
    """Move every IndicatorSnapshot owned by this report to new_date (C05 §7.1).

    Fetches candidates in two batched queries, delegates the collision
    decision to the pure `plan_snapshot_retarget`, then applies the plan:
      - no existing row at new_date for that indicator -> move this row.
      - existing row at new_date belongs to this same report (self-collision,
        e.g. undoing a prior edit) -> consolidate onto it (D05 §5
        unification rule) and drop the now-redundant row.
      - existing row at new_date belongs to a *different* analysis -> abort
        the whole edit with DateCollisionError, nothing written (all-or-nothing).
    """
    report_id_str = str(report.id)
    own_rows_result = await db.execute(
        select(IndicatorSnapshot).where(
            IndicatorSnapshot.source == "ai_analysis",
            IndicatorSnapshot.source_ref == report_id_str,
        )
    )
    own_rows = list(own_rows_result.scalars().all())
    if not own_rows:
        return

    indicator_ids = [row.indicator_id for row in own_rows]
    subject_type = own_rows[0].subject_type
    subject_id = own_rows[0].subject_id
    existing_result = await db.execute(
        select(IndicatorSnapshot).where(
            IndicatorSnapshot.indicator_id.in_(indicator_ids),
            IndicatorSnapshot.subject_type == subject_type,
            IndicatorSnapshot.subject_id == subject_id,
            IndicatorSnapshot.as_of_date == new_date,
        )
    )
    existing_by_indicator = {row.indicator_id: row for row in existing_result.scalars().all()}

    plan = plan_snapshot_retarget(
        own_rows, existing_by_indicator, report_id_str=report_id_str, new_date=new_date,
    )

    for row, other_self_row in plan:
        if other_self_row is None:
            row.as_of_date = new_date
        else:
            other_self_row.value_numeric = row.value_numeric
            other_self_row.value_text = row.value_text
            await db.delete(row)


# ── Delete report (§9.3) ──────────────────────────────────────────────────────


async def delete_report(
    db: AsyncSession,
    report: AnalysisReport,
) -> None:
    """Hard-delete a report and all its derived artifacts (§9.3).

    Cascade order:
      1. Delete IndicatorSnapshots with source='ai_analysis' and source_ref=report.id
      2. Delete AnalysisJob → ORM cascade deletes AnalysisReport
      3. Delete UploadedFile

    Caller must call await db.commit() after this function.
    """
    report_id_str = str(report.id)

    # 1. Remove indicator snapshots produced by this analysis
    await db.execute(
        delete(IndicatorSnapshot).where(
            IndicatorSnapshot.source == "ai_analysis",
            IndicatorSnapshot.source_ref == report_id_str,
        )
    )

    # 2. Load the job to get the uploaded_file reference
    job = await db.get(AnalysisJob, report.analysis_job_id)
    uf_id = job.uploaded_file_id if job else None

    if job:
        # Deleting the job cascades (ORM cascade="all, delete-orphan") to the report
        await db.delete(job)
    else:
        # Fallback: delete the orphaned report directly
        await db.delete(report)

    # 3. Delete the uploaded file
    if uf_id:
        uf = await db.get(UploadedFile, uf_id)
        if uf:
            await db.delete(uf)
