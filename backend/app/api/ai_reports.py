"""AI Report Analysis API endpoints — Spec D07.

All write endpoints are nested under /portfolios/{pid}/holdings/{hid}/ to enforce
portfolio ownership before the upload is accepted. Read/delete endpoints use a flat
/ai-reports/{...} prefix with per-report ownership checks via UploadedFile.user_id.

Endpoints:
    POST   /portfolios/{pid}/holdings/{hid}/ai-reports          — upload PDF, enqueue job
    GET    /portfolios/{pid}/holdings/{hid}/ai-reports          — list reports for holding
    GET    /ai-reports/jobs                                     — list jobs for current user
    GET    /ai-reports/{report_id}                              — get one report (full detail)
    DELETE /ai-reports/{report_id}                              — delete report + cascade
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d07_schemas import (
    AnalysisJobResponse,
    AnalysisReportDetail,
    AnalysisReportSummary,
    UploadReportResponse,
)
from app.auth.dependencies import get_current_user
from app.config import get_config
from app.db.models.user import User
from app.db.session import get_db
from app.services import ai_report_service
from app.services.portfolio_service import get_portfolio_by_id

# Two sub-routers; both are exported as `router` via a combined APIRouter at EOF.
_nested_router = APIRouter(
    prefix="/portfolios/{portfolio_id}/holdings/{holding_id}/ai-reports",
    tags=["ai-reports"],
)
_flat_router = APIRouter(prefix="/ai-reports", tags=["ai-reports"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _require_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User,
    db: AsyncSession,
):
    """Verify portfolio belongs to user and holding belongs to that portfolio."""
    from sqlalchemy import select

    from app.db.models.holding import Holding

    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    result = await db.execute(
        select(Holding).where(
            Holding.id == holding_id,
            Holding.portfolio_id == portfolio_id,
        )
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Holding not found.")

    if portfolio.archived_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Cannot upload to an archived portfolio.",
        )
    return holding


# ── Nested endpoints (upload + list) ─────────────────────────────────────────


@_nested_router.post(
    "",
    response_model=UploadReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_report(
    portfolio_id: UUID,
    holding_id: UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadReportResponse:
    """Upload a financial report PDF and enqueue an AI analysis job.

    Returns 202 Accepted immediately; processing is asynchronous.
    Poll GET /ai-reports/jobs to check status.
    """
    cfg = get_config()
    await _require_holding(portfolio_id, holding_id, current_user, db)

    content = await file.read()
    try:
        ai_report_service.validate_pdf(
            content=content,
            filename=file.filename or "upload.pdf",
            max_size_mb=cfg.uploads.max_file_size_mb,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = await ai_report_service.create_upload_and_job(
        db=db,
        user_id=current_user.id,
        holding_id=holding_id,
        content=content,
        filename=file.filename or "upload.pdf",
        mime_type="application/pdf",
    )

    return UploadReportResponse(
        job_id=job.id,
        status="queued",
        message=(
            "Tu informe se está procesando en segundo plano. "
            "Te avisaremos en la cabecera cuando esté listo."
        ),
    )


@_nested_router.get("", response_model=list[AnalysisReportSummary])
async def list_reports(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisReportSummary]:
    """List all analysis reports for a holding, newest first."""
    await _require_holding(portfolio_id, holding_id, current_user, db)
    reports = await ai_report_service.get_reports_for_holding(db, holding_id)
    return [AnalysisReportSummary.model_validate(r) for r in reports]


# ── Flat endpoints (jobs list must come before /{report_id} for correct routing) ─


@_flat_router.get("/jobs", response_model=list[AnalysisJobResponse])
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = None,
) -> list[AnalysisJobResponse]:
    """Return recent analysis jobs for the current user.

    Use ?status_filter=queued,running to filter by comma-separated statuses.
    Frontend polls this endpoint (Spec D07 §10, default every 30 s).
    """
    statuses = [s.strip() for s in status_filter.split(",")] if status_filter else None
    jobs = await ai_report_service.get_jobs_for_user(db, current_user.id, statuses=statuses)
    return [AnalysisJobResponse.model_validate(j) for j in jobs]


@_flat_router.get("/{report_id}", response_model=AnalysisReportDetail)
async def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisReportDetail:
    """Return full detail for one analysis report."""
    report = await ai_report_service.get_report(db, report_id, current_user.id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return AnalysisReportDetail.model_validate(report)


@_flat_router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an analysis report and all its derived artifacts (§9.3).

    Cascades to: AnalysisJob, UploadedFile, linked IndicatorSnapshots.
    This action is irreversible.
    """
    report = await ai_report_service.get_report(db, report_id, current_user.id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found.")

    await ai_report_service.delete_report(db, report)
    await db.commit()


# ── Combined router (include AFTER decorators are applied) ────────────────────
# NOTE: include_router copies routes at call time; it must run after all @router
# decorators above have registered their routes into _nested_router and _flat_router.

router = APIRouter()
router.include_router(_nested_router)
router.include_router(_flat_router)
