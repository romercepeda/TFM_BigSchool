"""Pydantic schemas for portfolio request bodies and responses — Spec D02.

These describe the API contract for /portfolios/* endpoints.
Separate from the ORM model (app/db/models/portfolio.py), which describes the database.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# v1 supported base currencies (Spec D02 §2).
BaseCurrency = Literal["EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD"]


# ── Request bodies ────────────────────────────────────────────────────────────


class CreatePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    base_currency: BaseCurrency


class RenamePortfolioRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


# ── Response bodies ───────────────────────────────────────────────────────────


class PortfolioResponse(BaseModel):
    id: UUID
    name: str
    base_currency: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = {"from_attributes": True}
