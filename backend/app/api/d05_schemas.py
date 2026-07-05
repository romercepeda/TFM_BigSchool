"""Pydantic schemas for D05 — Indicator Catalog & Historical Snapshots.

D08 note: IndicatorOut.name is the resolved translation of name_key, set by the
endpoint after model_validate(). SnapshotOut.value_text_display is the translated
categorical state label for qualitative indicators (e.g. 'golden_cross' → 'Cruce
Dorado'), also set by the endpoint. Raw values (name_key, value_text) are always
included so clients can use their own translation if preferred.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class IndicatorOut(BaseModel):
    id: UUID
    code: str
    name_key: str
    # Resolved translation of name_key for the request's language (D08 §5.4).
    name: str = ""
    description_key: str
    scope: str
    nature: str
    data_type: str
    unit: str | None
    update_strategy: str
    threshold_config: dict[str, Any]
    active: bool

    model_config = {"from_attributes": True}


class SnapshotOut(BaseModel):
    id: UUID
    as_of_date: date
    value_numeric: Decimal | None
    value_text: str | None
    # Translated label for categorical (qualitative) snapshots (D08 §5.4).
    # None for quantitative indicators or when value_text is None.
    value_text_display: str | None = None
    zone: str | None
    source: str
    created_at: datetime
    # Report period name of the AnalysisReport that produced this value
    # (Changeset C05 §8). Always None for source='scheduled_job'.
    source_report_name: str | None = None


class IndicatorSnapshotHistoryOut(BaseModel):
    """An indicator catalog entry paired with its current + last 2 snapshots (D05 §7)."""
    indicator: IndicatorOut
    snapshots: list[SnapshotOut]
