"""Pydantic schemas for portfolio request bodies and responses — Spec D02.

These describe the API contract for /portfolios/* endpoints.
Separate from the ORM model (app/db/models/portfolio.py), which describes the database.
"""

from datetime import date, datetime
from decimal import Decimal
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


# ── Portfolio summary (Changeset C08) ─────────────────────────────────────────


class TrendPoint(BaseModel):
    """One day of the 30-day trend series (Changeset C08 §4).

    estimated=True means the value uses a last-known-previous-close fallback
    (for price and/or FX rate) rather than an exact match for `date` — per
    Spec D09 §4.3, missing data is flagged, never silently invented.
    """
    date: date
    value: Decimal
    estimated: bool


class PortfolioSummary(BaseModel):
    """PortfolioHeader payload (Changeset C08 §3, extended by D13 §8 and
    D15 §7) — Valor Total, Invertido, P&L Latente, P&L Real, Dividendos, and
    the 30-day trend. All monetary fields are in the portfolio's base_currency.

    unrealized_pnl only ever reflected currently-held units (D13 §8 makes this
    explicit rather than changing behavior). realized_pnl is the sum of
    realized_gain_base across every sale in the portfolio. dividend_income is
    the sum of gross_amount_base across every DividendPayment in the
    portfolio (D15 §7), kept as its own bucket rather than folded into
    realized_pnl since dividends and capital gains are taxed differently in
    Spain (D15 §2). total_pnl/total_pnl_pct (added post-v1, user feedback:
    the header had no single figure reflecting the combined result — only
    the per-holding/per-portfolio list rows did) = unrealized_pnl +
    realized_pnl + dividend_income, against total_invested — same convention
    as PortfolioListSummary.total_pnl_pct below. unrealized_pnl itself is
    deliberately left unchanged by this addition: it still means exactly
    "paper gain from price movement, nothing else."
    """
    total_value: Decimal
    total_invested: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    dividend_income: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
    trend_30d: list[TrendPoint]
    computed_at: datetime
    base_currency: str


class PortfolioListSummary(BaseModel):
    """One row for the Portfolios listing screen (Spec D13 §9, extended by
    D15 §7.2) — assets count, currently-invested amount, and combined P&L
    (unrealized + realized + dividend income), one per portfolio the user
    owns. total_pnl_pct is against total_invested (currently-invested
    capital), matching unrealized_pnl_pct's denominator — not
    total_invested_ever (D13 §8's realized_pnl_pct denominator), which would
    understate the return once a portfolio is mostly cashed out.
    """
    id: UUID
    name: str
    base_currency: str
    status: str
    assets_count: int
    total_invested: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    dividend_income: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
