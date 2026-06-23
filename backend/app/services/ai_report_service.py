"""AI Report Analysis service layer — Spec D07.

Responsibilities:
  - PDF validation (content sniffing + size check)
  - UploadedFile + AnalysisJob creation, Celery task enqueue
  - Query helpers: reports for a holding, single report, pending jobs
  - Delete report (cascade to job, uploaded file, indicator snapshots)
  - Load prompt template and extraction schema (cached at module level)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_report import AnalysisJob, AnalysisReport, UploadedFile
from app.db.models.indicator import IndicatorSnapshot

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
    analyze_report_task.delay(str(job.id))
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
