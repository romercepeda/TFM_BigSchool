"""Portfolio summary service — Changeset C08, extended by Spec D13 §8 / Changeset C20 §6.

Computes the portfolioHeader values (Valor Total, Invertido, P&L Latente, P&L
Real, and the 30-day trend) from data already persisted by Spec D09
(AssetPriceHistory, FxRateHistory), the existing FX engine (Spec D04), and
each holding's Sale rows (Spec D13). No new tables, no new provider calls:
"today" reuses the same last-known-price/last-known-fx-rate lookup as every
other day in the 30-day window, rather than a live fetch.

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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.portfolio_schemas import PortfolioListSummary, PortfolioSummary, TrendPoint
from app.db.models.dividend import AssetDividendSchedule
from app.db.models.holding import Holding
from app.db.models.lot import Lot
from app.db.models.market_data import AssetPriceHistory, FxRateHistory
from app.db.models.portfolio import Portfolio
from app.db.models.sale import SaleLotConsumption
from app.services import dividend_service, fx_engine, summary_cache
from app.services.fx_engine import LotCalcInput
from app.services.portfolio_service import list_portfolios as list_portfolios_query

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
    # One entry per sale on this holding: (sale_date, realized_gain_base).
    # None means that sale's realized_gain_base couldn't be computed
    # (unresolved FX at creation, or a pre-D13 sale the backfill migration
    # couldn't reconstruct) — excluded from the aggregate rather than treated
    # as zero. A future-dated sale (sale_date > today) is also excluded until
    # its date arrives, matching how _quantity_remaining_at treats a
    # future-dated consumption as not-yet-happened for the unrealized side —
    # otherwise the same units would count as both still-held (unrealized)
    # and already-sold (realized) on the same day.
    sales: tuple[tuple[date, Decimal | None], ...] = ()
    # One entry per DividendPayment on this holding: (payment_date,
    # gross_amount_base). Same None/future-date exclusion rules as `sales`
    # (Spec D15 par.7, mirrors D13 par.8's rule exactly, same as the bug
    # C20 par.6 already found and fixed once for sales).
    dividend_payments: tuple[tuple[date, Decimal | None], ...] = ()


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


def _compute_realized_totals(holdings: list[HoldingSnapshot], today: date) -> tuple[Decimal, Decimal]:
    """Changeset C20 §6 / Spec D13 §8 — realized_pnl, realized_pnl_pct.

    realized_pnl sums every sale's realized_gain_base across the portfolio's
    holdings, excluding: sales whose gain couldn't be computed (same "no
    invented values" principle as the trend/current-totals computations
    above), and sales dated after `today` — a future-dated sale hasn't
    happened yet, so counting its gain now while its units still count as
    held (unrealized) would double-count the same position.

    total_invested_ever (the denominator) is the base-currency cost of every
    lot ever created, consumed or not, regardless of date — each lot's own
    fx_rate_at_purchase is used, same as cost-basis elsewhere; a lot with
    unresolved FX is excluded. This corrects D13 §8's literal text (a
    quote-currency sum, which would mix currencies across holdings quoted
    differently) to match Changeset C20 §6's formula, which already converts
    to base currency.
    """
    realized_pnl = _ZERO
    total_invested_ever = _ZERO

    for holding in holdings:
        for sale_date, gain in holding.sales:
            if gain is not None and sale_date <= today:
                realized_pnl += gain
        for lot in holding.lots:
            if lot.fx_rate_at_purchase is not None:
                total_invested_ever += lot.quantity * lot.unit_price * lot.fx_rate_at_purchase

    realized_pnl_pct = (realized_pnl / total_invested_ever) if total_invested_ever > _ZERO else _ZERO
    return _round(realized_pnl), _round(realized_pnl_pct, _Q_RETURN)


def _compute_dividend_income(holdings: list[HoldingSnapshot], today: date) -> Decimal:
    """Spec D15 §7 — sum of gross_amount_base across every DividendPayment in
    the portfolio, excluding: payments whose base-currency amount couldn't be
    computed (unresolved FX at creation, same "no invented values" principle
    as realized_pnl), and payments dated after `today` (mirrors D13/C20 §6's
    future-dated-sale exclusion exactly, to avoid the same double-counting
    class of bug for dividends).
    """
    dividend_income = _ZERO
    for holding in holdings:
        for payment_date, amount in holding.dividend_payments:
            if amount is not None and payment_date <= today:
                dividend_income += amount
    return _round(dividend_income)


# ── Per-holding P&L breakdown (Spec D13 §10, Changeset C20 §8) ───────────────


@dataclass(frozen=True)
class HoldingPnl:
    """One holding's row for the portfolio dashboard's asset list (D13 §10).

    Unknowable current-market figures (no price/fx ever recorded for this
    holding) default to zero rather than None — every holding still needs a
    row, so "excluded from the aggregate" (as in _compute_current_totals)
    becomes "zero contribution" here. The frontend distinguishes "sold out"
    (active_units == 0) from "no market data yet" the same way either way:
    invested/unrealized_pnl read as zero.
    """
    holding_id: UUID
    active_units: Decimal
    invested: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    dividend_income: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
    # Spec D15 §4 — None whenever not computable (no schedule, irregular
    # frequency, zero dividend/cost-basis, unresolved current FX rate).
    dividend_coverage_years: Decimal | None


def _compute_holding_pnl(
    holding: HoldingSnapshot,
    price_index: dict[UUID, _SeriesIndex],
    fx_index: dict[tuple[str, str], _SeriesIndex],
    base_currency: str,
    today: date,
    schedule: AssetDividendSchedule | None,
) -> HoldingPnl:
    active_units = sum((_quantity_remaining_at(lot, today) for lot in holding.lots), _ZERO)

    realized_pnl = _ZERO
    for sale_date, gain in holding.sales:
        if gain is not None and sale_date <= today:
            realized_pnl += gain

    dividend_income = _ZERO
    for payment_date, amount in holding.dividend_payments:
        if amount is not None and payment_date <= today:
            dividend_income += amount

    invested = _ZERO
    unrealized_pnl = _ZERO
    fx_rate: Decimal | None = None

    price_result = _last_known(price_index.get(holding.asset_id), today)
    if price_result is not None:
        current_price, _price_date = price_result

        fx_rate = Decimal("1")
        if holding.quote_currency != base_currency:
            fx_result = _last_known(fx_index.get((holding.quote_currency, base_currency)), today)
            fx_rate = fx_result[0] if fx_result is not None else None

        if fx_rate is not None:
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
                invested = calc.total_cost_base
            if calc.total_value_base is not None:
                unrealized_pnl = calc.total_value_base - invested

    total_pnl = unrealized_pnl + realized_pnl + dividend_income
    total_pnl_pct = (total_pnl / invested) if invested > _ZERO else _ZERO

    # D15 §4.1 — avg cost of currently-held units in base currency, derived
    # the same way as lot_service.compute_holding_aggregates' weighted
    # average (invested / active_units), without a second lot-level pass.
    avg_purchase_price_base = (invested / active_units) if active_units > _ZERO else _ZERO
    dividend_coverage_years = dividend_service.compute_dividend_coverage_years(
        avg_purchase_price_base, schedule, fx_rate
    )

    return HoldingPnl(
        holding_id=holding.holding_id,
        active_units=_round(active_units),
        invested=_round(invested),
        unrealized_pnl=_round(unrealized_pnl),
        realized_pnl=_round(realized_pnl),
        dividend_income=_round(dividend_income),
        total_pnl=_round(total_pnl),
        total_pnl_pct=_round(total_pnl_pct, _Q_RETURN),
        dividend_coverage_years=dividend_coverage_years,
    )


def compute_holding_summaries(
    holdings: list[HoldingSnapshot],
    prices: dict[UUID, _Series],
    fx_rates: dict[tuple[str, str], _Series],
    base_currency: str,
    today: date,
    schedules: dict[UUID, AssetDividendSchedule] | None = None,
) -> list[HoldingPnl]:
    """Pure entry point for the per-holding dashboard rows (D13 §10) — one
    row per holding, not aggregated. Deliberately not shared code with
    _compute_current_totals (the portfolio-level aggregate): the two round
    at different points (per-holding here vs. once at the portfolio sum
    there), so sharing would either change the aggregate's existing,
    already-tested rounding or complicate this simpler per-row path.

    `schedules` is keyed by asset_id (Spec D15 §4.4) — optional so existing
    callers/tests that don't care about the dividend indicator still work.
    """
    price_index = {asset_id: _build_index(series) for asset_id, series in prices.items()}
    fx_index = {pair: _build_index(series) for pair, series in fx_rates.items()}
    schedules = schedules or {}
    return [
        _compute_holding_pnl(
            holding, price_index, fx_index, base_currency, today,
            schedules.get(holding.asset_id),
        )
        for holding in holdings
    ]


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
    realized_pnl, realized_pnl_pct = _compute_realized_totals(holdings, today)
    dividend_income = _compute_dividend_income(holdings, today)

    if not holdings:
        return PortfolioSummary(
            total_value=_ZERO,
            total_invested=_ZERO,
            unrealized_pnl=_ZERO,
            unrealized_pnl_pct=_ZERO,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            dividend_income=dividend_income,
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
        realized_pnl=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        dividend_income=dividend_income,
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
            selectinload(Holding.sales),  # D13 §8 — realized_pnl aggregate
            selectinload(Holding.dividend_payments),  # D15 §7 — dividend_income aggregate
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
                sales=tuple((s.sale_date, s.realized_gain_base) for s in holding.sales),
                dividend_payments=tuple(
                    (p.payment_date, p.gross_amount_base) for p in holding.dividend_payments
                ),
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


async def get_holding_summaries(db: AsyncSession, portfolio: Portfolio) -> list[HoldingPnl]:
    """Per-holding dashboard rows for a portfolio (Spec D13 §10, Changeset C20 §8).

    Reuses the exact same thin fetchers as get_summary() (one query each for
    holdings/lots, prices, FX) — not cached separately from the portfolio
    summary cache, since this is a distinct read shape or from it, but cheap
    enough (same query pattern) that a personal-portfolio's holding count
    doesn't warrant its own cache layer.
    """
    today = date.today()
    holdings = await _fetch_holding_snapshots(db, portfolio.id)
    if not holdings:
        return []

    asset_ids = {h.asset_id for h in holdings}
    pairs = {
        (h.quote_currency, portfolio.base_currency)
        for h in holdings
        if h.quote_currency != portfolio.base_currency
    }
    prices = await _fetch_price_series(db, asset_ids, today)
    fx_rates = await _fetch_fx_series(db, pairs, today)
    schedules = await dividend_service.get_schedules_for_assets(db, asset_ids)

    return compute_holding_summaries(
        holdings, prices, fx_rates, portfolio.base_currency, today, schedules
    )


async def get_last_known_fx_rate(
    db: AsyncSession, quote_currency: str, base_currency: str, as_of: date
) -> Decimal | None:
    """Cache-only FX lookup (Spec D15 §4.1) — the latest known rate with
    as_of_date <= as_of, reusing the same _last_known() pattern as the rest
    of this module. Deliberately does NOT call the live provider: per
    Changeset C19, a GET must not trigger a live network fetch on every page
    view. Same-currency pairs return 1 without a query.
    """
    if quote_currency == base_currency:
        return Decimal("1")
    series = await _fetch_fx_series(db, {(quote_currency, base_currency)}, as_of)
    index = _build_index(series.get((quote_currency, base_currency), []))
    result = _last_known(index, as_of)
    return result[0] if result is not None else None


async def _fetch_active_holdings_count(
    db: AsyncSession, portfolio_ids: list[UUID]
) -> dict[UUID, int]:
    """Number of distinct holdings with active_units > 0, per portfolio (D13 §9).

    A direct SQL aggregate over the live quantity_consumed column — assets_count
    is inherently a "right now" figure (unlike the date-reconstructed trend/
    current-totals above), so no as-of-date lot-history logic is needed here.
    One query for every portfolio in `portfolio_ids`, not one per portfolio.
    """
    if not portfolio_ids:
        return {}
    result = await db.execute(
        select(
            Holding.portfolio_id,
            Holding.id,
            func.sum(Lot.quantity - Lot.quantity_consumed),
        )
        .join(Lot, Lot.holding_id == Holding.id)
        .where(Holding.portfolio_id.in_(portfolio_ids))
        .group_by(Holding.portfolio_id, Holding.id)
    )
    counts: dict[UUID, int] = {}
    for portfolio_id, _holding_id, remaining in result.all():
        if remaining is not None and remaining > _ZERO:
            counts[portfolio_id] = counts.get(portfolio_id, 0) + 1
    return counts


async def get_portfolio_list_summaries(
    db: AsyncSession, user_id: UUID, *, include_archived: bool = False
) -> list[PortfolioListSummary]:
    """One lightweight summary per portfolio the user owns (Spec D13 §9), in a
    single round trip for the Portfolios listing screen.

    Reuses get_summary() per portfolio (so it benefits from the same 5-minute
    cache as the portfolio header) rather than a bespoke cross-portfolio SQL
    aggregate — at personal-portfolio scale (a handful of portfolios per
    user), N calls to an already-cached, already-tested computation is a
    better trade than a parallel aggregate query path that would need its
    own testing and could drift from get_summary()'s figures. assets_count is
    the one piece fetched in a single dedicated query across all portfolios,
    since it isn't part of PortfolioSummary at all.
    """
    portfolios = await list_portfolios_query(db, user_id, include_archived=include_archived)
    if not portfolios:
        return []

    active_counts = await _fetch_active_holdings_count(db, [p.id for p in portfolios])

    results = []
    for portfolio in portfolios:
        summary = await get_summary(db, portfolio, user_id)
        total_pnl = summary.unrealized_pnl + summary.realized_pnl + summary.dividend_income
        total_pnl_pct = (
            (total_pnl / summary.total_invested) if summary.total_invested > _ZERO else _ZERO
        )
        results.append(PortfolioListSummary(
            id=portfolio.id,
            name=portfolio.name,
            base_currency=portfolio.base_currency,
            status=portfolio.status,
            assets_count=active_counts.get(portfolio.id, 0),
            total_invested=summary.total_invested,
            unrealized_pnl=summary.unrealized_pnl,
            realized_pnl=summary.realized_pnl,
            dividend_income=summary.dividend_income,
            total_pnl=_round(total_pnl),
            total_pnl_pct=_round(total_pnl_pct, _Q_RETURN),
        ))
    return results
