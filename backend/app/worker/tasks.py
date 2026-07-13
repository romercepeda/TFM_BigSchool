"""Celery tasks — Spec D07 §6.1 & §7.

analyze_report_task: the single async PDF analysis task.

Retry policy (non-configurable per spec §7):
    Max 3 total attempts. Backoff: 60 s → 300 s → 900 s.
    Config / auth errors go straight to failed (NonRetryableError).

asyncio.run() is used to call async service functions from the sync Celery task.
A NullPool engine is created per invocation so each event loop gets fresh connections.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.worker import celery_app

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [60, 300, 900]  # seconds: after 0th, 1st, 2nd failure


# ── NonRetryableError ─────────────────────────────────────────────────────────


class NonRetryableError(Exception):
    """Raised for config/auth errors that will repeat identically — skip retries."""


# ── DB session factory for worker (NullPool: no shared pool across event loops) ──


def _make_db_session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Report date / name resolution (Changeset C05 §5) ──────────────────────────

_REPORT_PERIOD_NAME_MAX_LEN = 40


def _resolve_report_date(
    report_date_str: str | None, *, today: date, job_id: str,
) -> tuple[date, str]:
    """Resolve the as_of_date for a report and its provenance (C05 §5).

    A missing, unparsable, or future-dated report_date falls back to today
    (the processing date) rather than blocking the analysis — a future date
    is never a legitimate fiscal reference point, so it is treated the same
    as a null extraction.
    """
    if report_date_str:
        try:
            parsed = date.fromisoformat(report_date_str)
        except ValueError:
            logger.warning(
                "Job %s: invalid report_date %r — using upload-date fallback.",
                job_id, report_date_str,
            )
        else:
            if parsed > today:
                logger.warning(
                    "Job %s: report_date %s is in the future — using upload-date fallback.",
                    job_id, parsed,
                )
            else:
                return parsed, "ai_extracted"
    return today, "upload_fallback"


def _resolve_report_period_name(raw_name: str | None) -> str | None:
    """Trim/normalize the AI-extracted report period name (C05 §3).

    Truncated defensively to the DB column length so an overly verbose AI
    response never fails the insert.
    """
    if not raw_name:
        return None
    name = raw_name.strip()
    return name[:_REPORT_PERIOD_NAME_MAX_LEN] if name else None


# ── Core async analysis logic ─────────────────────────────────────────────────


async def _run_analysis(job_id: str) -> None:
    """Full analysis pipeline. Raises on any failure (retryable or not)."""
    from app.config import get_config
    from app.db.models.ai_report import AnalysisJob, AnalysisReport, UploadedFile
    from app.services.ai_providers.factory import (
        NonRetryableError as FactoryError,
    )
    from app.services.ai_providers.factory import (
        get_ai_provider,
    )
    from app.services.ai_report_service import fetch_system_context, load_prompt, load_schema

    cfg = get_config()
    SessionLocal = _make_db_session()  # noqa: N806
    now = datetime.now(UTC)

    async with SessionLocal() as db:
        job = await db.get(AnalysisJob, UUID(job_id))
        if job is None:
            raise NonRetryableError(f"Job {job_id} not found in database.")

        # Mark as running
        provider_name = cfg.ai.provider
        job.status = "running"
        job.provider = provider_name
        job.attempt_count = (job.attempt_count or 0) + 1
        if job.started_at is None:
            job.started_at = now
        await db.commit()

        # Load PDF bytes
        uploaded_file = await db.get(UploadedFile, job.uploaded_file_id)
        if uploaded_file is None:
            raise NonRetryableError(f"UploadedFile for job {job_id} not found.")
        pdf_bytes = uploaded_file.content

        # Load holding → asset context
        from sqlalchemy.orm import selectinload

        from app.db.models.holding import Holding

        holding_result = await db.execute(
            select(Holding)
            .where(Holding.id == job.holding_id)
            .options(selectinload(Holding.asset))
        )
        holding = holding_result.scalar_one_or_none()
        if holding is None:
            raise NonRetryableError(f"Holding for job {job_id} not found.")

        asset_context = {
            "ticker": holding.asset.ticker,
            "name": holding.asset.name,
            "asset_type": holding.asset.asset_type,
            "quote_currency": holding.asset.quote_currency,
        }

        # Resolve AI provider
        try:
            provider = get_ai_provider(cfg)
        except FactoryError as exc:
            raise NonRetryableError(str(exc)) from exc

        # Load prompt and schema (cached after first startup)
        prompt_template = load_prompt()
        schema = load_schema()

        # Fetch system context (price + prior indicator history) to enrich the prompt.
        # Failures are silently swallowed inside fetch_system_context — never aborts the job.
        system_context = await fetch_system_context(
            asset_id=holding.asset_id,
            quote_currency=holding.asset.quote_currency,
            db=db,
        )
        logger.debug("Job %s: system context keys=%s", job_id, list(system_context.keys()))

        # Call the LLM
        result = await provider.extract_from_pdf(
            pdf_bytes, prompt_template, schema, asset_context, system_context
        )
        job.model_version = result.model_version

        if not result.succeeded:
            # Schema/parse failure — record error and raise to trigger retry
            error_msg = f"[{result.parse_status}] {result.error or 'unknown parse error'}"
            raise ValueError(error_msg)

        # Build AnalysisReport
        extracted = result.parsed_json  # type: ignore[index]

        # Asset/file correspondence check (Changeset C05) — a mismatch is a
        # deterministic content problem, not a transient failure, so it goes
        # straight to failed without retrying and without creating a report.
        if extracted.get("asset_match") is False:
            notes = extracted.get("asset_match_notes")
            detail = f" {notes}" if notes else ""
            raise NonRetryableError(
                f"The uploaded file does not appear to correspond to "
                f"{asset_context['ticker']} ({asset_context['name']}).{detail}"
            )
        report_date, report_date_source = _resolve_report_date(
            extracted.get("report_date"), today=now.date(), job_id=job_id,
        )
        report_period_name = _resolve_report_period_name(extracted.get("report_period_name"))
        report_period_name_source = "ai_extracted" if report_period_name else "unset"

        report = AnalysisReport(
            holding_id=job.holding_id,
            asset_id=holding.asset_id,
            uploaded_file_id=job.uploaded_file_id,
            analysis_job_id=job.id,
            report_date=report_date,
            report_date_source=report_date_source,
            report_period_name=report_period_name,
            report_period_name_source=report_period_name_source,
            provider=provider_name,
            model_version=result.model_version,
            extracted_metrics=extracted.get("metrics", {}),
            executive_summary_es=extracted.get("executive_summary_es", ""),
            executive_summary_en=extracted.get("executive_summary_en", ""),
            global_signal=extracted.get("global_signal"),
            confidence_notes=extracted.get("confidence_notes"),
            raw_response={"text": result.raw_response},
        )
        db.add(report)
        await db.flush()  # assign report.id

        # Write IndicatorSnapshots for on_ai_analysis fundamentals
        snap_date = report_date
        await _write_indicator_snapshots(
            db=db,
            asset_id=holding.asset_id,
            metrics=extracted.get("metrics", {}),
            report_id=report.id,
            as_of_date=snap_date,
        )

        # Finalize job
        job.status = "succeeded"
        job.analysis_report_id = report.id
        job.completed_at = datetime.now(UTC)
        await db.commit()
        logger.info("Job %s succeeded. Report id=%s", job_id, report.id)


async def _write_indicator_snapshots(
    db: AsyncSession,
    asset_id: UUID,
    metrics: dict,
    report_id: UUID,
    as_of_date: date,
) -> None:
    """Upsert IndicatorSnapshots for all on_ai_analysis indicators (D07 §9.2).

    Uses the same ON CONFLICT DO UPDATE pattern as D05 run_daily_indicators.
    """
    from app.db.models.indicator import Indicator, IndicatorSnapshot

    result = await db.execute(
        select(Indicator).where(
            Indicator.update_strategy == "on_ai_analysis",
            Indicator.ai_extraction_key.isnot(None),
            Indicator.active.is_(True),
        )
    )
    indicators = list(result.scalars().all())
    now = datetime.now(UTC)

    for indicator in indicators:
        key = indicator.ai_extraction_key
        if key not in metrics:
            continue

        raw_value = metrics[key]
        value_numeric: Decimal | None = None
        value_text: str | None = None

        if indicator.data_type == "quantitative":
            if raw_value is not None:
                try:
                    value_numeric = Decimal(str(raw_value))
                except Exception:
                    logger.warning("Could not convert %r to Decimal for %s", raw_value, key)
        else:
            value_text = str(raw_value) if raw_value is not None else None

        if value_numeric is None and value_text is None:
            # Changeset C15: the AI didn't disclose this metric in this report.
            # Skip rather than upsert a null — matches run_daily_indicators'
            # "insufficient data — silently skip" rule, and avoids overwriting
            # a real value from an earlier report with nothing.
            continue

        stmt = (
            pg_insert(IndicatorSnapshot)
            .values(
                indicator_id=indicator.id,
                subject_type="asset",
                subject_id=asset_id,
                as_of_date=as_of_date,
                value_numeric=value_numeric,
                value_text=value_text,
                source="ai_analysis",
                source_ref=str(report_id),
                created_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_snapshot_indicator_subject_date",
                set_={
                    "value_numeric": value_numeric,
                    "value_text": value_text,
                    "source": "ai_analysis",
                    "source_ref": str(report_id),
                },
            )
        )
        await db.execute(stmt)


async def _set_job_failed(job_id: str, error_msg: str) -> None:
    """Persist failed status on the AnalysisJob row."""
    from app.db.models.ai_report import AnalysisJob

    SessionLocal = _make_db_session()  # noqa: N806
    async with SessionLocal() as db:
        job = await db.get(AnalysisJob, UUID(job_id))
        if job:
            job.status = "failed"
            job.last_error = error_msg[:500]
            job.completed_at = datetime.now(UTC)
            await db.commit()
            logger.error("Job %s failed: %s", job_id, error_msg[:200])


# ── Celery task ───────────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=2, name="app.worker.tasks.analyze_report_task")
def analyze_report_task(self, job_id: str) -> None:
    """Process one queued AnalysisJob. Retries up to 3 total attempts."""
    try:
        asyncio.run(_run_analysis(job_id))
    except NonRetryableError as exc:
        asyncio.run(_set_job_failed(job_id, str(exc)))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            countdown = _RETRY_DELAYS[self.request.retries]
            logger.warning(
                "Job %s attempt %d failed (%s) — retrying in %ds.",
                job_id, self.request.retries + 1, type(exc).__name__, countdown,
            )
            raise self.retry(exc=exc, countdown=countdown) from exc
        # Max retries exhausted
        asyncio.run(_set_job_failed(job_id, str(exc)))
