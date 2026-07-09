"""AI Report Analysis API endpoints — Spec D07, Changeset C05.

All write endpoints are nested under /portfolios/{pid}/holdings/{hid}/ to enforce
portfolio ownership before the upload is accepted. Read/edit/delete endpoints use a
flat /ai-reports/{...} prefix with per-report ownership checks via UploadedFile.user_id.

Endpoints:
    POST   /portfolios/{pid}/holdings/{hid}/ai-reports          — upload PDF, enqueue job
    GET    /portfolios/{pid}/holdings/{hid}/ai-reports          — list reports for holding
    GET    /ai-reports/jobs                                     — list jobs for current user
    GET    /ai-reports/{report_id}                              — get one report (full detail)
    PATCH  /ai-reports/{report_id}                              — edit report_date/name (C05 §7)
    DELETE /ai-reports/{report_id}                              — delete report + cascade
"""

import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d07_schemas import (
    AnalysisJobResponse,
    AnalysisReportDetail,
    AnalysisReportPatchRequest,
    AnalysisReportSummary,
    UploadReportResponse,
)
from app.auth.dependencies import get_current_user
from app.config import get_config
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services import ai_report_service
from app.services.portfolio_service import get_portfolio_by_id

# Two sub-routers; both are exported as `router` via a combined APIRouter at EOF.
_nested_router = APIRouter(
    prefix="/portfolios/{portfolio_id}/holdings/{holding_id}/ai-reports",
    tags=["ai-reports"],
)
_flat_router = APIRouter(prefix="/ai-reports", tags=["ai-reports"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _analysis_edit_enabled() -> bool:
    """Changeset C05 §11 Step 6 — flipped to true now that the history-screen
    editing UI (Step 6) ships alongside this endpoint. Set
    ENABLE_ANALYSIS_EDIT=false to disable without a redeploy if needed."""
    return os.environ.get("ENABLE_ANALYSIS_EDIT", "true").strip().lower() == "true"


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
    dependencies=[Depends(require_permission("analysis.upload"))],
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


@_nested_router.get(
    "",
    response_model=list[AnalysisReportSummary],
    dependencies=[Depends(require_permission("analysis.view"))],
)
async def list_reports(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisReportSummary]:
    """List all analysis reports for the holding's asset, newest first.

    Shared across every user who holds this asset (Changeset C13) — not
    limited to the requesting holding_id, which is only used to establish
    that the current user is authorized to see this asset's history at all.
    """
    holding = await _require_holding(portfolio_id, holding_id, current_user, db)
    reports = await ai_report_service.get_reports_for_asset(
        db, holding.asset_id, current_user_id=current_user.id
    )
    return [AnalysisReportSummary(**r) for r in reports]


# ── Flat endpoints (jobs list must come before /{report_id} for correct routing) ─


@_flat_router.get(
    "/jobs",
    response_model=list[AnalysisJobResponse],
    dependencies=[Depends(require_permission("analysis.view"))],
)
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


@_flat_router.get(
    "/{report_id}",
    response_model=AnalysisReportDetail,
    dependencies=[Depends(require_permission("analysis.view"))],
)
async def get_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisReportDetail:
    """Return full detail for one analysis report.

    Viewable by the uploader or by any user who currently holds the same
    asset in one of their own portfolios (Changeset C13) — editing/deleting
    remain uploader-only, see patch_report/delete_report below.
    """
    report = await ai_report_service.get_viewable_report(db, report_id, current_user.id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found.")
    is_own = await ai_report_service.get_own_report(db, report_id, current_user.id) is not None
    return AnalysisReportDetail.model_validate(report).model_copy(update={"is_own": is_own})


@_flat_router.patch(
    "/{report_id}",
    response_model=AnalysisReportDetail,
    dependencies=[Depends(require_permission("analysis.edit"))],
)
async def patch_report(
    report_id: UUID,
    body: AnalysisReportPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisReportDetail:
    """Edit report_date and/or report_period_name (Changeset C05 §7).

    Updates the report row and, when the date changes, every derived
    IndicatorSnapshot's as_of_date atomically. A date collision with another
    analysis's snapshot is rejected with 409 (§7.1) and leaves nothing written.
    """
    if not _analysis_edit_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found.")

    report = await ai_report_service.get_own_report(db, report_id, current_user.id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found.")

    if body.report_period_name is not None and len(body.report_period_name) > 40:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="report_period_name must be at most 40 characters.",
        )

    try:
        updated = await ai_report_service.update_report_metadata(
            db,
            report,
            new_report_date=body.report_date,
            new_report_period_name=body.report_period_name,
        )
    except ai_report_service.DateCollisionError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Another analysis already exists with this date for this asset.",
        ) from exc

    await db.commit()
    await db.refresh(updated)
    # get_own_report already proved current_user is the uploader — is_own is
    # always true on a successful edit.
    return AnalysisReportDetail.model_validate(updated).model_copy(update={"is_own": True})


@_flat_router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("analysis.delete"))],
)
async def delete_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an analysis report and all its derived artifacts (§9.3).

    Cascades to: AnalysisJob, UploadedFile, linked IndicatorSnapshots.
    This action is irreversible. Uploader-only (Changeset C13) — sharing the
    Historial view does not extend to deleting someone else's analysis.
    """
    report = await ai_report_service.get_own_report(db, report_id, current_user.id)
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
