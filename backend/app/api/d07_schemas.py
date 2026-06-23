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
    """Short representation shown in the Historial list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    holding_id: UUID
    report_date: date | None
    provider: str
    model_version: str
    global_signal: str | None
    executive_summary: str
    created_at: datetime


class AnalysisReportDetail(BaseModel):
    """Full detail view including extracted metrics and raw response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    holding_id: UUID
    uploaded_file_id: UUID | None
    analysis_job_id: UUID
    report_date: date | None
    provider: str
    model_version: str
    extracted_metrics: dict
    executive_summary: str
    global_signal: str | None
    confidence_notes: str | None
    created_at: datetime
