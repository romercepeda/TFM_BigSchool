"""Pydantic schemas for D05 — Indicator Catalog & Historical Snapshots."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class IndicatorOut(BaseModel):
    id: UUID
    code: str
    name_key: str
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
    zone: str | None
    source: str
    created_at: datetime


class IndicatorSnapshotHistoryOut(BaseModel):
    """An indicator catalog entry paired with its current + last 2 snapshots (D05 §7)."""
    indicator: IndicatorOut
    snapshots: list[SnapshotOut]
