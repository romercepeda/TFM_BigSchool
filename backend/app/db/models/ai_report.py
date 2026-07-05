"""AI Report Analysis ORM entities — Spec D07.

Three tables:
    UploadedFile    — raw PDF bytes (BYTEA), linked to a Holding and User
    AnalysisJob     — async Celery task lifecycle (queued → running → succeeded/failed)
    AnalysisReport  — immutable outcome of a successful analysis

Cascade on Holding delete (DB-level):
    UploadedFile, AnalysisJob, and AnalysisReport all have holding_id FKs with
    ondelete=CASCADE so a Holding deletion removes all three automatically.

Cascade on user-initiated report delete (service-layer):
    Service deletes AnalysisJob → ORM cascade deletes AnalysisReport →
    service explicitly deletes UploadedFile and IndicatorSnapshots (§9.3).

Note: AnalysisJob.analysis_report_id is a plain UUID (no FK) to avoid a circular
foreign key between analysis_jobs and analysis_reports. Integrity is enforced at the
service layer.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_AI_PROVIDER_ENUM = Enum("anthropic", "openai", "gemini", name="ai_provider_enum")
_JOB_STATUS_ENUM = Enum(
    "queued", "running", "succeeded", "failed", name="analysis_job_status_enum"
)
_GLOBAL_SIGNAL_ENUM = Enum("bullish", "neutral", "bearish", name="global_signal_enum")
# "legacy_unknown" exists only for the backfill of pre-C05 rows (Changeset C05 §4);
# new rows only ever use the other three values.
_REPORT_DATE_SOURCE_ENUM = Enum(
    "ai_extracted", "upload_fallback", "user_edited", "legacy_unknown",
    name="report_date_source_enum",
)
_REPORT_PERIOD_NAME_SOURCE_ENUM = Enum(
    "ai_extracted", "user_edited", "unset", name="report_period_name_source_enum",
)


class UploadedFile(Base):
    """Stores the raw PDF bytes for one analysis upload."""

    __tablename__ = "uploaded_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="uploaded_file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<UploadedFile id={self.id} filename={self.original_filename!r}>"


class AnalysisJob(Base):
    """Tracks one Celery task lifecycle. Deleted cascades to its AnalysisReport."""

    __tablename__ = "analysis_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(_AI_PROVIDER_ENUM, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        _JOB_STATUS_ENUM, nullable=False, default="queued"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Application-level reference — not a FK to avoid circular constraint.
    analysis_report_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    uploaded_file: Mapped["UploadedFile | None"] = relationship(
        back_populates="jobs",
    )
    reports: Mapped[list["AnalysisReport"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AnalysisJob id={self.id} status={self.status!r}>"


class AnalysisReport(Base):
    """Outcome of a successful analysis. User-deletable (§9.3).

    report_date and report_period_name are editable after creation via
    PATCH /analyses/{id} (Changeset C05 §7) — no longer fully immutable.
    """

    __tablename__ = "analysis_reports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    holding_id: Mapped[UUID] = mapped_column(
        ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_file_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True
    )
    analysis_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False
    )
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_date_source: Mapped[str] = mapped_column(
        _REPORT_DATE_SOURCE_ENUM, nullable=False, default="ai_extracted"
    )
    report_period_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    report_period_name_source: Mapped[str] = mapped_column(
        _REPORT_PERIOD_NAME_SOURCE_ENUM, nullable=False, default="unset"
    )
    provider: Mapped[str] = mapped_column(_AI_PROVIDER_ENUM, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    global_signal: Mapped[str | None] = mapped_column(_GLOBAL_SIGNAL_ENUM, nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped["AnalysisJob"] = relationship(back_populates="reports")

    def __repr__(self) -> str:
        return f"<AnalysisReport id={self.id} holding_id={self.holding_id}>"
