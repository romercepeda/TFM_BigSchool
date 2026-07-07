"""Portfolio summary service — Changeset C08.

Computes the portfolioHeader values (Valor Total, Invertido, P&L Latente, and
the 30-day trend) from data already persisted by Spec D09 (AssetPriceHistory,
FxRateHistory) and the existing FX engine (Spec D04). No new tables, no new
provider calls: "today" reuses the same last-known-price/last-known-fx-rate
lookup as every other day in the 30-day window, rather than a live fetch.

Split in two layers, matching this project's testing convention (Spec 00c —
DB-touching paths are verified manually; automated tests cover pure logic):
  - compute_summary() and its helpers: pure functions, no I/O, no clock
    (mirrors app.services.fx_engine). This is the 90%+-covered surface.
  - _fetch_*(): thin async DB queries feeding the pure layer. Verified
    manually against the dev database, like Changeset C04's Settings API.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.portfolio_schemas import PortfolioSummary, TrendPoint
from app.db.models.holding import Holding
from app.db.models.lot import Lot
from app.db.models.market_data import AssetPriceHistory, FxRateHistory
from app.db.models.portfolio import Portfolio
from app.db.models.sale import SaleLotConsumption
from app.services import fx_engine, summary_cache
from app.services.fx_engine import LotCalcInput

_Q_MONETARY = Decimal("0.00000001")  # 8 dp, matches fx_engine's monetary precision (D04)
_Q_RETURN = Decimal("0.0001")        # 4 dp, matches fx_engine's return precision (D04)
_ZERO = Decimal("0")
_TREND_DAYS = 30

# (date, value) points ordered ascending by date.
_Series = list[tuple[date, Decimal]]
# Precomputed for bisect: parallel list of dates and list of values.
_SeriesIndex = tuple[list[date], list[Decimal]]


def _round(value: Decimal, quant: Decimal = _Q_MONETARY) -> Decimal:
    return value.quantize(quant, rounding=ROUND_HALF_EVEN)


# ── Pure data model (no ORM, no I/O) ──────────────────────────────────────────


@dataclass(frozen=True)
class LotSnapshot:
    """Everything compute_summary() needs from one Lot, plus its FIFO
    consumption history (Spec D03 §7.2) so remaining quantity can be
    reconstructed as of any past date, not just today.
    """
    lot_id: UUID
    purchase_date: date
    quantity: Decimal
    unit_price: Decimal
    fx_rate_at_purchase: Decimal | None
    # (sale_date, quantity_consumed) — one entry per SaleLotConsumption row.
    consumptions: tuple[tuple[date, Decimal], ...]


@dataclass(frozen=True)
class HoldingSnapshot:
    holding_id: UUID
    asset_id: UUID
    quote_currency: str
    lots: tuple[LotSnapshot, ...]


# ── Pure helpers ───────────────────────────────────────────────────────────────


def _build_index(series: _Series) -> _SeriesIndex:
    dates = [d for d, _ in series]
    values = [v for _, v in series]
    return dates, values


def _last_known(index: _SeriesIndex | None, on_date: date) -> tuple[Decimal, date] | None:
    """Return (value, matched_date) for the latest entry with date <= on_date.

    None if the index is empty/missing or every entry is after on_date.
    """
    if index is None:
        return None
    dates, values = index
    idx = bisect.bisect_right(dates, on_date) - 1
    if idx < 0:
        return None
    return values[idx], dates[idx]


def _quantity_remaining_at(lot: LotSnapshot, on_date: date) -> Decimal:
    """Reconstruct a lot's remaining quantity as of a past date.

    Uses each consumption's actual sale_date rather than the lot's current
    (as-of-today) quantity_consumed, so a sale dated after on_date correctly
    does not reduce the position on that day.
    """
    if lot.purchase_date > on_date:
        return _ZERO
    consumed = sum(
        (qty for sale_date, qty in lot.consumptions if sale_date <= on_date),
        _ZERO,
    )
    return lot.quantity - consumed


def _compute_trend_30d(
    holdings: list[HoldingSnapshot],
    price_index: dict[UUID, _SeriesIndex],
    fx_index: dict[tuple[str, str], _SeriesIndex],
    base_currency: str,
    today: date,
) -> list[TrendPoint]:
    """Changeset C08 §4 — one point per day, oldest first.

    A holding with no priceable data at or before a given day is excluded
    from that day's sum (not the whole computation); if it is the only
    holding with data missing that day is still marked estimated, since the
    total no longer reflects the full portfolio. A day with zero
    contributing holdings is omitted entirely rather than shown as 0.
    """
    points: list[TrendPoint] = []

    for offset in range(_TREND_DAYS - 1, -1, -1):
        day = today - timedelta(days=offset)
        day_total = _ZERO
        day_has_contribution = False
        day_estimated = False

        for holding in holdings:
            remaining_by_lot = [
                (lot, _quantity_remaining_at(lot, day)) for lot in holding.lots
            ]
            remaining = sum((q for _, q in remaining_by_lot), _ZERO)
            if remaining <= _ZERO:
                continue

            price_result = _last_known(price_index.get(holding.asset_id), day)
            if price_result is None:
                # Never priced as of this date — exclude just this holding.
                day_estimated = True
                continue
            price, price_date = price_result
            if price_date != day:
                day_estimated = True

            if holding.quote_currency == base_currency:
                fx_rate = Decimal("1")
            else:
                fx_result = _last_known(fx_index.get((holding.quote_currency, base_currency)), day)
                if fx_result is None:
                    day_estimated = True
                    continue
                fx_rate, fx_date = fx_result
                if fx_date != day:
                    day_estimated = True

            day_total += remaining * price * fx_rate
            day_has_contribution = True

        if not day_has_contribution:
            continue

        points.append(TrendPoint(date=day, value=_round(day_total), estimated=day_estimated))

    return points


def _compute_current_totals(
    holdings: list[HoldingSnapshot],
    price_index: dict[UUID, _SeriesIndex],
    fx_index: dict[tuple[str, str], _SeriesIndex],
    base_currency: str,
    today: date,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Changeset C08 §3 — total_value, total_invested, unrealized_pnl, unrealized_pnl_pct.

    Reuses fx_engine.calculate_holding (Spec D04) per holding, fed with the
    same last-known price/fx lookup used for "today" in the trend series. A
    holding with no priceable data at all is excluded from these totals too
    (fx_engine requires a non-null current price) — same "no invented
    values" principle as the trend computation.
    """
    total_value = _ZERO
    total_invested = _ZERO

    for holding in holdings:
        price_result = _last_known(price_index.get(holding.asset_id), today)
        if price_result is None:
            continue
        current_price, _price_date = price_result

        if holding.quote_currency == base_currency:
            fx_rate = Decimal("1")
        else:
            fx_result = _last_known(fx_index.get((holding.quote_currency, base_currency)), today)
            if fx_result is None:
                continue
            fx_rate, _fx_date = fx_result

        lot_inputs = [
            LotCalcInput(
                lot_id=lot.lot_id,
                quantity_remaining=_quantity_remaining_at(lot, today),
                unit_price_at_purchase=lot.unit_price,
                fx_rate_at_purchase=lot.fx_rate_at_purchase,
                current_unit_price=current_price,
                fx_rate_current=fx_rate,
            )
            for lot in holding.lots
        ]
        calc = fx_engine.calculate_holding(lot_inputs)
        if calc.total_cost_base is not None:
            total_invested += calc.total_cost_base
        if calc.total_value_base is not None:
            total_value += calc.total_value_base

    unrealized_pnl = total_value - total_invested
    unrealized_pnl_pct = (unrealized_pnl / total_invested) if total_invested > _ZERO else _ZERO

    return (
        _round(total_value),
        _round(total_invested),
        _round(unrealized_pnl),
        _round(unrealized_pnl_pct, _Q_RETURN),
    )


def compute_summary(
    holdings: list[HoldingSnapshot],
    prices: dict[UUID, _Series],
    fx_rates: dict[tuple[str, str], _Series],
    base_currency: str,
    today: date,
    now: datetime,
) -> PortfolioSummary:
    """Pure aggregation entry point — no DB, no network, no internal clock.

    `today` and `now` are passed in by the caller (mirrors fx_engine's "no
    clock" rule) so this function is fully deterministic and unit-testable.
    """
    if not holdings:
        return PortfolioSummary(
            total_value=_ZERO,
            total_invested=_ZERO,
            unrealized_pnl=_ZERO,
            unrealized_pnl_pct=_ZERO,
            trend_30d=[],
            computed_at=now,
            base_currency=base_currency,
        )

    price_index = {asset_id: _build_index(series) for asset_id, series in prices.items()}
    fx_index = {pair: _build_index(series) for pair, series in fx_rates.items()}

    trend_30d = _compute_trend_30d(holdings, price_index, fx_index, base_currency, today)
    total_value, total_invested, unrealized_pnl, unrealized_pnl_pct = _compute_current_totals(
        holdings, price_index, fx_index, base_currency, today
    )

    return PortfolioSummary(
        total_value=total_value,
        total_invested=total_invested,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        trend_30d=trend_30d,
        computed_at=now,
        base_currency=base_currency,
    )


# ── Thin DB-fetching layer (verified manually against the dev database) ──────


async def _fetch_holding_snapshots(db: AsyncSession, portfolio_id: UUID) -> list[HoldingSnapshot]:
    result = await db.execute(
        select(Holding)
        .where(Holding.portfolio_id == portfolio_id)
        .options(
            selectinload(Holding.asset),
            selectinload(Holding.lots)
            .selectinload(Lot.sale_consumptions)
            .selectinload(SaleLotConsumption.sale),
        )
    )
    holdings = result.scalars().all()

    snapshots = []
    for holding in holdings:
        lots = tuple(
            LotSnapshot(
                lot_id=lot.id,
                purchase_date=lot.purchase_date,
                quantity=lot.quantity,
                unit_price=lot.unit_price,
                fx_rate_at_purchase=lot.fx_rate_at_purchase,
                consumptions=tuple(
                    sorted(
                        (c.sale.sale_date, c.quantity_consumed)
                        for c in lot.sale_consumptions
                    )
                ),
            )
            for lot in holding.lots
        )
        snapshots.append(
            HoldingSnapshot(
                holding_id=holding.id,
                asset_id=holding.asset_id,
                quote_currency=holding.asset.quote_currency,
                lots=lots,
            )
        )
    return snapshots


async def _fetch_price_series(
    db: AsyncSession, asset_ids: set[UUID], as_of: date
) -> dict[UUID, _Series]:
    if not asset_ids:
        return {}
    result = await db.execute(
        select(AssetPriceHistory)
        .where(
            AssetPriceHistory.asset_id.in_(asset_ids),
            AssetPriceHistory.as_of_date <= as_of,
        )
        .order_by(AssetPriceHistory.asset_id, AssetPriceHistory.as_of_date.asc())
    )
    series: dict[UUID, _Series] = {}
    for row in result.scalars().all():
        series.setdefault(row.asset_id, []).append((row.as_of_date, row.close_price))
    return series


async def _fetch_fx_series(
    db: AsyncSession, pairs: set[tuple[str, str]], as_of: date
) -> dict[tuple[str, str], _Series]:
    if not pairs:
        return {}
    quote_currencies = {q for q, _ in pairs}
    base_currencies = {b for _, b in pairs}
    result = await db.execute(
        select(FxRateHistory)
        .where(
            FxRateHistory.quote_currency.in_(quote_currencies),
            FxRateHistory.base_currency.in_(base_currencies),
            FxRateHistory.as_of_date <= as_of,
        )
        .order_by(
            FxRateHistory.quote_currency,
            FxRateHistory.base_currency,
            FxRateHistory.as_of_date.asc(),
        )
    )
    series: dict[tuple[str, str], _Series] = {}
    for row in result.scalars().all():
        pair = (row.quote_currency, row.base_currency)
        if pair in pairs:
            series.setdefault(pair, []).append((row.as_of_date, row.rate))
    return series


async def get_summary(db: AsyncSession, portfolio: Portfolio, user_id: UUID) -> PortfolioSummary:
    """Compute the portfolioHeader summary for an already-loaded, owned Portfolio.

    Caller (the API endpoint) is responsible for the 404-on-not-owned check,
    same pattern as rename_portfolio/archive_portfolio in portfolio_service.
    Checks the 5-minute TTL cache (Changeset C08 §5) before touching the DB.
    """
    cached = summary_cache.get_cached(portfolio.id, user_id)
    if cached is not None:
        return cached

    today = date.today()
    now = datetime.now(UTC)

    holdings = await _fetch_holding_snapshots(db, portfolio.id)
    if not holdings:
        summary = compute_summary(holdings, {}, {}, portfolio.base_currency, today, now)
    else:
        asset_ids = {h.asset_id for h in holdings}
        pairs = {
            (h.quote_currency, portfolio.base_currency)
            for h in holdings
            if h.quote_currency != portfolio.base_currency
        }

        prices = await _fetch_price_series(db, asset_ids, today)
        fx_rates = await _fetch_fx_series(db, pairs, today)

        summary = compute_summary(holdings, prices, fx_rates, portfolio.base_currency, today, now)

    summary_cache.store(portfolio.id, user_id, summary)
    return summary
