"""Indicator Catalog & Historical Snapshots service — Spec D05.

Responsibilities:
  - Load indicators_catalog.yaml at startup and upsert to DB (§3.1)
  - Validate calculator registry at startup (§8)
  - Compute scheduled_daily technical indicators from price history
  - Evaluate zones from threshold configs at display time (§7.2)
  - Serve current + last 2 previous snapshots per indicator (§7)
"""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset
from app.db.models.indicator import Indicator, IndicatorSnapshot
from app.db.models.market_data import AssetPriceHistory

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).parent.parent.parent / "indicators_catalog.yaml"

# ── Return type for calculators ───────────────────────────────────────────────

CalcResult = tuple[Decimal | None, str | None]  # (value_numeric, value_text)

# ── Helper: EMA (Wilder's style, k = 2/(period+1)) ───────────────────────────


def _ema(prices: list[Decimal], period: int) -> Decimal:
    k = Decimal(2) / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema


# ── Technical calculators ─────────────────────────────────────────────────────


def calc_ma_200(prices: list[Decimal]) -> CalcResult:
    """200-day simple moving average. Snapshot stores the MA value (reference)."""
    if len(prices) < 200:
        return None, None
    ma = sum(prices[-200:]) / 200
    return Decimal(str(round(float(ma), 8))), None


def calc_ma_50_200_cross(prices: list[Decimal]) -> CalcResult:
    """MA50/MA200 cross state. Returns value_text: golden_cross|near_cross|death_cross."""
    if len(prices) < 200:
        return None, None
    ma50 = sum(prices[-50:]) / 50
    ma200 = sum(prices[-200:]) / 200
    diff_pct = (ma50 - ma200) / ma200
    if diff_pct > Decimal("0.02"):
        return None, "golden_cross"
    if diff_pct < Decimal("-0.02"):
        return None, "death_cross"
    return None, "near_cross"


def calc_rsi_14(prices: list[Decimal]) -> CalcResult:
    """RSI(14) using Wilder's smoothing. Returns 0–100 numeric value."""
    period = 14
    if len(prices) < period + 1:
        return None, None
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    avg_gain = sum(max(c, Decimal(0)) for c in changes[:period]) / period
    avg_loss = sum(max(-c, Decimal(0)) for c in changes[:period]) / period
    for c in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(c, Decimal(0))) / period
        avg_loss = (avg_loss * (period - 1) + max(-c, Decimal(0))) / period
    if avg_loss == 0:
        return Decimal("100"), None
    rs = avg_gain / avg_loss
    rsi = Decimal("100") - Decimal("100") / (1 + rs)
    return Decimal(str(round(float(rsi), 4))), None


def calc_macd(prices: list[Decimal]) -> CalcResult:
    """MACD = EMA(12) − EMA(26). Requires at least 26 price points."""
    if len(prices) < 26:
        return None, None
    macd_val = _ema(prices, 12) - _ema(prices, 26)
    return Decimal(str(round(float(macd_val), 8))), None


def calc_rvol(prices: list[Decimal], *, volumes: list[int | None] | None = None) -> CalcResult:
    if not volumes or len(volumes) < 21:
        return None, None
    recent = volumes[-21:]
    if any(v is None for v in recent):
        return None, None
    avg_20 = sum(recent[:-1]) / 20
    if avg_20 == 0:
        return None, None
    return Decimal(str(round(recent[-1] / avg_20, 4))), None


# ── Fundamental stubs (populated by D07 AI analysis) ─────────────────────────


def pull_from_latest_ai_analysis(prices: list[Decimal]) -> CalcResult:
    # D07 writes snapshots directly; daily job never calls this (on_ai_analysis strategy).
    return None, None


# ── Portfolio KPI stubs (computed on demand at endpoint) ─────────────────────


def calc_portfolio_twr(prices: list[Decimal]) -> CalcResult:
    return None, None


def calc_portfolio_cagr(prices: list[Decimal]) -> CalcResult:
    return None, None


def calc_portfolio_max_drawdown(prices: list[Decimal]) -> CalcResult:
    return None, None


def calc_portfolio_volatility(prices: list[Decimal]) -> CalcResult:
    return None, None


def calc_portfolio_sharpe(prices: list[Decimal]) -> CalcResult:
    return None, None


# ── Calculator registry ───────────────────────────────────────────────────────

CALCULATOR_REGISTRY: dict[str, Any] = {
    "calc_ma_200": calc_ma_200,
    "calc_ma_50_200_cross": calc_ma_50_200_cross,
    "calc_rsi_14": calc_rsi_14,
    "calc_macd": calc_macd,
    "calc_rvol": calc_rvol,
    "pull_from_latest_ai_analysis": pull_from_latest_ai_analysis,
    "calc_portfolio_twr": calc_portfolio_twr,
    "calc_portfolio_cagr": calc_portfolio_cagr,
    "calc_portfolio_max_drawdown": calc_portfolio_max_drawdown,
    "calc_portfolio_volatility": calc_portfolio_volatility,
    "calc_portfolio_sharpe": calc_portfolio_sharpe,
}

# ── Zone evaluation (D05 §4) ──────────────────────────────────────────────────


def evaluate_zone(
    threshold_config: dict,
    value_numeric: Decimal | None,
    value_text: str | None,
    close_price: Decimal | None = None,
    previous_value_numeric: Decimal | None = None,
) -> str | None:
    """Return 'positive', 'neutral', 'attention', or None (informational / no data).

    Zones are always computed from the current threshold_config regardless of snapshot age.
    For price_vs_reference, close_price is the asset's close price for that snapshot date.
    For signed_with_trend, previous_value_numeric is the prior snapshot's value.
    """
    model = threshold_config.get("model")

    if model == "informational_only":
        return None

    if model == "numeric_thresholds":
        if value_numeric is None:
            return None
        return _eval_three_zones(
            value_numeric,
            threshold_config["positive"],
            threshold_config["neutral"],
            threshold_config["attention"],
        )

    if model == "three_band_numeric":
        if value_numeric is None:
            return None
        v = value_numeric
        bands = [
            (threshold_config["attention_low"], "attention"),
            (threshold_config["neutral_low"], "neutral"),
            (threshold_config["positive"], "positive"),
            (threshold_config["neutral_high"], "neutral"),
            (threshold_config["attention_high"], "attention"),
        ]
        for band, zone in bands:
            if _in_band(v, band):
                return zone
        return "neutral"

    if model == "price_vs_reference":
        if value_numeric is None or close_price is None:
            return None
        ref = value_numeric
        band = Decimal(str(threshold_config.get("neutral_band_pct", 0.02)))
        if close_price > ref * (1 + band):
            return "positive"
        if close_price < ref * (1 - band):
            return "attention"
        return "neutral"

    if model == "signed_with_trend":
        if value_numeric is None:
            return None
        near_zero = Decimal(str(threshold_config.get("near_zero_threshold", 0.5)))
        v = value_numeric
        if abs(v) <= near_zero:
            return "neutral"
        if v > 0 and previous_value_numeric is not None and v > previous_value_numeric:
            return "positive"
        if v < 0 and previous_value_numeric is not None and v < previous_value_numeric:
            return "attention"
        return "neutral"

    if model == "categorical_state":
        if value_text is None:
            return None
        return threshold_config.get("mapping", {}).get(value_text)

    return None


def _in_band(v: Decimal, band: dict) -> bool:
    min_val = band.get("min")
    max_val = band.get("max")
    if min_val is not None and v < Decimal(str(min_val)):
        return False
    if max_val is not None and v >= Decimal(str(max_val)):
        return False
    return True


def _eval_three_zones(v: Decimal, pos: dict, neu: dict, att: dict) -> str:
    if _in_band(v, pos):
        return "positive"
    if _in_band(v, neu):
        return "neutral"
    return "attention"


# ── Seed loading (D05 §3.1) ───────────────────────────────────────────────────


async def seed_indicators(db: AsyncSession) -> None:
    """Upsert indicators_catalog.yaml into the DB. Fails fast on missing calculators.

    Called at application startup. Per spec §3.1:
    - new entry → insert
    - existing code → update mutable fields
    - code removed from catalog → mark active=False (snapshots retained)
    """
    if not _CATALOG_PATH.exists():
        logger.critical("indicators_catalog.yaml not found at %s — cannot start.", _CATALOG_PATH)
        raise SystemExit(1)

    with open(_CATALOG_PATH) as f:
        catalog = yaml.safe_load(f) or {}

    entries: list[dict] = catalog.get("indicators", [])
    catalog_codes = {e["code"] for e in entries}

    # Validate all calculators are registered before any DB writes.
    for entry in entries:
        code = entry["calculator_code"]
        if code not in CALCULATOR_REGISTRY:
            logger.critical(
                "Indicator %r references unregistered calculator %r — cannot start.",
                entry["code"], code,
            )
            raise SystemExit(1)

    now = datetime.now(UTC)

    for entry in entries:
        existing = await db.scalar(
            select(Indicator).where(Indicator.code == entry["code"])
        )
        if existing is None:
            db.add(Indicator(
                code=entry["code"],
                name_key=entry["name_key"],
                description_key=entry["description_key"],
                scope=entry["scope"],
                nature=entry["nature"],
                data_type=entry["data_type"],
                unit=entry.get("unit"),
                calculator_code=entry["calculator_code"],
                ai_extraction_key=entry.get("ai_extraction_key"),
                update_strategy=entry["update_strategy"],
                threshold_config=entry["threshold_config"],
                active=True,
            ))
        else:
            existing.name_key = entry["name_key"]
            existing.description_key = entry["description_key"]
            existing.unit = entry.get("unit")
            existing.calculator_code = entry["calculator_code"]
            existing.ai_extraction_key = entry.get("ai_extraction_key")
            existing.threshold_config = entry["threshold_config"]
            existing.active = True
            existing.updated_at = now

    # Deactivate indicators removed from the catalog.
    all_rows = await db.execute(select(Indicator))
    for ind in all_rows.scalars().all():
        if ind.code not in catalog_codes and ind.active:
            ind.active = False
            ind.updated_at = now

    await db.commit()
    logger.info("Indicator catalog seeded: %d indicators.", len(entries))


# ── Daily technical indicator computation (D05 §6.1) ─────────────────────────


async def run_daily_indicators(
    db: AsyncSession,
    asset: Asset,
    prices: list[Decimal],
    as_of_date: date,
    *,
    volumes: list[int | None] | None = None,
) -> int:
    """Compute all active scheduled_daily asset indicators and upsert snapshots.

    prices: close prices sorted oldest-first (from the daily update job).
    Returns the number of snapshots written (created or updated).
    If a calculator returns (None, None), the indicator is silently skipped (§6.1).
    Errors on individual indicators are logged and do not abort other indicators (§6.1).
    """
    indicators_result = await db.execute(
        select(Indicator).where(
            Indicator.scope == "asset",
            Indicator.update_strategy == "scheduled_daily",
            Indicator.active.is_(True),
        )
    )
    indicators = list(indicators_result.scalars().all())
    written = 0
    now = datetime.now(UTC)

    for indicator in indicators:
        try:
            calc = CALCULATOR_REGISTRY[indicator.calculator_code]
            if indicator.calculator_code == 'calc_rvol':
                value_numeric, value_text = calc(prices, volumes=volumes)
            else:
                value_numeric, value_text = calc(prices)
        except Exception as exc:
            logger.error(
                "Calculator %r failed for %s / %s: %s",
                indicator.calculator_code, asset.ticker, indicator.code, exc,
            )
            continue

        if value_numeric is None and value_text is None:
            continue  # insufficient data — silently skip

        stmt = (
            pg_insert(IndicatorSnapshot)
            .values(
                indicator_id=indicator.id,
                subject_type="asset",
                subject_id=asset.id,
                as_of_date=as_of_date,
                value_numeric=value_numeric,
                value_text=value_text,
                source="scheduled_job",
                source_ref=None,
                created_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_snapshot_indicator_subject_date",
                set_={
                    "value_numeric": value_numeric,
                    "value_text": value_text,
                },
            )
        )
        await db.execute(stmt)
        written += 1

    return written


# ── Query helpers ─────────────────────────────────────────────────────────────


async def get_indicators_by_scope(db: AsyncSession, scope: str) -> list[Indicator]:
    result = await db.execute(
        select(Indicator).where(
            Indicator.scope == scope,
            Indicator.active.is_(True),
        ).order_by(Indicator.nature, Indicator.code)
    )
    return list(result.scalars().all())


async def get_asset_indicator_history(
    db: AsyncSession,
    asset_id: UUID,
    indicator: Indicator,
) -> list[dict]:
    """Return the most recent 3 snapshots for an asset + indicator, newest-first.

    Each dict includes the snapshot fields plus an evaluated 'zone'.
    For price_vs_reference indicators, AssetPriceHistory is joined to supply the
    close price needed for zone computation (D05 §4.3).
    """
    snapshots_result = await db.execute(
        select(IndicatorSnapshot)
        .where(
            IndicatorSnapshot.indicator_id == indicator.id,
            IndicatorSnapshot.subject_type == "asset",
            IndicatorSnapshot.subject_id == asset_id,
        )
        .order_by(IndicatorSnapshot.as_of_date.desc())
        .limit(3)
    )
    snapshots = list(snapshots_result.scalars().all())

    if not snapshots:
        return []

    # For price_vs_reference, look up close prices for the snapshot dates.
    close_prices: dict[date, Decimal] = {}
    if indicator.threshold_config.get("model") == "price_vs_reference":
        snap_dates = [s.as_of_date for s in snapshots]
        prices_result = await db.execute(
            select(AssetPriceHistory).where(
                AssetPriceHistory.asset_id == asset_id,
                AssetPriceHistory.as_of_date.in_(snap_dates),
            )
        )
        for row in prices_result.scalars().all():
            close_prices[row.as_of_date] = row.close_price

    result = []
    for i, snap in enumerate(snapshots):
        prev_snap = snapshots[i + 1] if i + 1 < len(snapshots) else None
        zone = evaluate_zone(
            indicator.threshold_config,
            snap.value_numeric,
            snap.value_text,
            close_price=close_prices.get(snap.as_of_date),
            previous_value_numeric=prev_snap.value_numeric if prev_snap else None,
        )
        result.append({
            "id": snap.id,
            "as_of_date": snap.as_of_date,
            "value_numeric": snap.value_numeric,
            "value_text": snap.value_text,
            "zone": zone,
            "source": snap.source,
            "created_at": snap.created_at,
        })

    return result
