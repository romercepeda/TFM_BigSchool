"""Pydantic schemas for the AI Report Analysis API — Spec D07."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UploadReportResponse(BaseModel):
    """Returned immediately after a successful PDF upload."""

    job_id: UUID
    status: str
    message: str


class AnalysisJobResponse(BaseModel):
    """Snapshot of a Celery job's lifecycle state."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    holding_id: UUID
    status: str
    provider: str | None
    model_version: str | None
    attempt_count: int
    last_error: str | None
    analysis_report_id: UUID | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AnalysisReportSummary(BaseModel):
    """Short representation shown in the Historial list.

    Shared across every user who holds the asset (Changeset C13) — holding_id
    is the report's originating holding (used for edit/delete ownership), not
    necessarily the requesting user's own holding. is_own tells the frontend
    whether to show edit/delete controls for this entry.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    holding_id: UUID
    asset_id: UUID
    report_date: date | None
    report_date_source: str
    report_period_name: str | None
    report_period_name_source: str
    provider: str
    model_version: str
    global_signal: str | None
    executive_summary_es: str
    executive_summary_en: str
    created_at: datetime
    is_own: bool


class AnalysisReportDetail(BaseModel):
    """Full detail view including extracted metrics and raw response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    holding_id: UUID
    asset_id: UUID
    uploaded_file_id: UUID | None
    analysis_job_id: UUID
    report_date: date | None
    report_date_source: str
    report_period_name: str | None
    report_period_name_source: str
    provider: str
    model_version: str
    extracted_metrics: dict
    executive_summary_es: str
    executive_summary_en: str
    global_signal: str | None
    confidence_notes: str | None
    created_at: datetime
    # Defaults False so model_validate(orm_report) succeeds (the ORM object
    # has no such attribute); the endpoint overrides it via model_copy once
    # it has computed the real value (Changeset C13).
    is_own: bool = False


class AnalysisReportPatchRequest(BaseModel):
    """Body for PATCH /ai-reports/{id} — Changeset C05 §7."""

    report_date: date | None = None
    report_period_name: str | None = None
