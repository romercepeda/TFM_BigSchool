# Spec D05 — Indicator Catalog & Historical Snapshots

**Status:** Approved
**Type:** Domain capability
**References:** Spec D03 (Asset Holdings), Spec D04 (FX Calculation Engine), Spec 00f (Global Configuration), Spec D07 (AI Report Analysis)

---

## 1. Purpose

Define the catalog of indicators the system supports (5 technical + 5 fundamental per asset, plus 5 portfolio-level KPIs in v1), how indicator values are computed and stored over time, and how the "current + last 2 previous" history shown to the user is derived from that storage.

The catalog is **data-driven**: indicators are defined in a seed file that populates the database on startup, and the application logic operates on whichever indicators happen to be present. Adding, modifying, or deactivating an indicator does not require code changes to the application's business logic, only changes to the seed file and (for new calculation formulas) registration of a corresponding calculator function.

---

## 2. Conceptual model

The data is layered in three levels:

1. **Indicator definition** — the catalog entry: name, description, scope (asset-level or portfolio-level), nature (technical, fundamental, portfolio KPI), data type (quantitative, qualitative), the thresholds for positive/neutral/attention zones, the unit of measurement, and a reference to its calculator function.
2. **Indicator snapshot** — a historical record: the value of one indicator for one asset (or portfolio) on a specific date.
3. **Indicator zone evaluation** — derived (not stored): given a snapshot's numeric value and the indicator's current thresholds, the zone (`positive` / `neutral` / `attention`) is computed at display time.

---

## 3. Indicator catalog

### 3.1 Storage: seed file + database

- The catalog is defined in a versioned seed file at the backend project root: **`indicators_catalog.yaml`**.
- On application startup, the seed file is read. For each entry: if no matching indicator exists in the database, it is created; if one exists with the same `code`, its mutable fields (description, thresholds, unit, active status) are updated; if an indicator exists in the database but no longer appears in the seed file, it is marked `inactive` (not deleted) so that historical snapshots remain interpretable.
- Adding a new indicator therefore requires: (1) editing the seed file with the new entry, (2) registering a calculator function in the calculator registry (only required if the calculation logic is new — many fundamental indicators reuse a generic "pull from latest AI analysis" calculator), and (3) restarting the backend. No domain code change is required to merely surface or hide an indicator.

### 3.2 `Indicator` entity

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key, auto-generated. |
| `code` | string | Stable, machine-readable identifier (e.g. `ma_200`, `rsi_14`, `per`, `twr`). Unique. Used in the seed file to match entries to existing rows. |
| `name_key` | string | i18n key for the user-facing name (e.g. `indicator.ma_200.name`). Actual translation handled by the i18n spec. |
| `description_key` | string | i18n key for the user-facing description. In v1, the resolved value is the same English description regardless of the user's language — by explicit decision (see Spec D08 §3.2). Future versions may provide localized translations of these descriptions. |
| `scope` | enum | `asset` \| `portfolio`. |
| `nature` | enum | `technical` \| `fundamental` \| `portfolio_kpi`. |
| `data_type` | enum | `quantitative` \| `qualitative`. |
| `unit` | string, nullable | Human-readable unit (e.g. `%`, `x`, `pp`, `EUR`). Null for qualitative indicators. |
| `calculator_code` | string | The code identifying which calculator function produces this indicator's value. Must be registered in the calculator registry on startup or the seed load fails. |
| `ai_extraction_key` | string, nullable | For indicators that derive their value from AI extraction (typically `update_strategy = on_ai_analysis`), the key under which the AI extraction schema returns the value (see Spec D07 §4.2). Null for indicators whose value is computed by code rather than extracted from an LLM response. |
| `update_strategy` | enum | `scheduled_daily` \| `on_ai_analysis` \| `on_demand_calculated`. See Section 6. |
| `threshold_config` | JSONB | Indicator-specific configuration of zone boundaries. Schema varies per indicator type — see Section 4. |
| `active` | boolean | `false` indicates the indicator is no longer in the seed file or has been disabled. Snapshots are retained but no new snapshots are created. |
| `created_at` | timestamp (UTC) | |
| `updated_at` | timestamp (UTC) | |

### 3.3 v1 catalog

Per the functional design, v1 ships with the following indicators. The seed file populates all of them. The exact threshold values shown here are reflected in the seed file; the table in this spec is the source of truth in case of any discrepancy.

**Asset-level technical (scope = `asset`, nature = `technical`, update_strategy = `scheduled_daily`):**

| code | name | unit | threshold model (Section 4) |
|---|---|---|---|
| `ma_200` | MA200 | (price) | `price_vs_reference` with ±2% neutral band |
| `ma_50_200_cross` | MA50/MA200 Cross | (state) | `categorical_state`: `golden_cross` / `near_cross` / `death_cross` |
| `rsi_14` | RSI 14 | (index) | `three_band_numeric`: positive 40–70, neutral 30–40 ∪ 70–80, attention <30 ∨ >80 |
| `macd` | MACD | (index) | `signed_with_trend`: positive sign + rising → positive; near zero → neutral; negative + falling → attention |
| `rvol` | Relative Volume | `x` | `numeric_thresholds`: positive >1.5, neutral 0.8–1.5, attention <0.8 |

**Asset-level fundamental (scope = `asset`, nature = `fundamental`, update_strategy = `on_ai_analysis`):**

| code | name | unit | threshold model |
|---|---|---|---|
| `per` | PER | (ratio) | `numeric_thresholds`: positive <15, neutral 15–25, attention >25 or negative |
| `roe` | ROE | `%` | `numeric_thresholds`: positive >15, neutral 8–15, attention <8 |
| `debt_ebitda` | Debt / EBITDA | `x` | `numeric_thresholds`: positive <2, neutral 2–4, attention >4 |
| `revenue_growth_yoy` | Revenue Growth (YoY) | `%` | `numeric_thresholds`: positive >8, neutral 0–8, attention <0 |
| `analyst_sentiment` | Analyst / Report Sentiment | (qualitative) | `categorical_state`: `bullish` / `mixed` / `bearish` |

**Portfolio-level (scope = `portfolio`, nature = `portfolio_kpi`, update_strategy = `on_demand_calculated`):**

| code | name | unit | threshold model |
|---|---|---|---|
| `twr` | Total Return (TWR) | `%` | `informational_only` — see Section 4.5 |
| `cagr` | Annualized Return (CAGR) | `%` | `informational_only` |
| `max_drawdown` | Maximum Drawdown | `%` | `informational_only` |
| `volatility` | Volatility | `%` | `informational_only` |
| `sharpe` | Sharpe Ratio | (ratio) | `informational_only` |

The portfolio-level KPIs are computed by formulas referenced in the original functional design and in Spec D04's separation note; they read the lot and FX data and produce a single number per portfolio. The detailed formulas for each KPI are part of the calculator registration and are tested per Spec 00c. They have no zone-classification thresholds in v1 because there is no universal "good" or "bad" threshold for them — they are presented to the user as numeric KPIs to be read in context. This is captured by the `informational_only` threshold model.

---

## 4. Threshold models

Each indicator has a `threshold_config` JSON document whose schema is determined by the indicator's threshold model. The supported models in v1 are listed below. Adding a new model **does** require code (a new evaluator), and is reserved for genuinely new shapes of evaluation logic.

### 4.1 `numeric_thresholds`

Two numeric boundaries split the real line into three zones.

```json
{
  "model": "numeric_thresholds",
  "positive": { "min": null, "max": 15 },
  "neutral":  { "min": 15,   "max": 25 },
  "attention":{ "min": 25,   "max": null }
}
```

Conventions: `min` is inclusive, `max` is exclusive. `null` means open-ended. Multiple-zone configurations (e.g. RSI's split attention zone) use the variant `three_band_numeric` (Section 4.2).

### 4.2 `three_band_numeric`

Used for indicators where the positive zone sits **between** two attention zones (the classic RSI shape).

```json
{
  "model": "three_band_numeric",
  "attention_low":  { "min": null, "max": 30 },
  "neutral_low":    { "min": 30,   "max": 40 },
  "positive":       { "min": 40,   "max": 70 },
  "neutral_high":   { "min": 70,   "max": 80 },
  "attention_high": { "min": 80,   "max": null }
}
```

The evaluator returns `positive` / `neutral` / `attention` based on which band the value falls in (neutral_low and neutral_high both map to `neutral`; attention_low and attention_high both map to `attention`).

### 4.3 `price_vs_reference`

Compares the current asset price against a reference value (e.g. MA200), with a neutral band expressed as a percentage of the reference.

```json
{
  "model": "price_vs_reference",
  "neutral_band_pct": 0.02
}
```

The snapshot for this indicator stores the **reference value** (e.g. the MA200 price). The evaluator computes:
- If `current_price > reference × (1 + neutral_band_pct)` → `positive`.
- If `current_price < reference × (1 − neutral_band_pct)` → `attention`.
- Otherwise → `neutral`.

### 4.4 `signed_with_trend`

Uses both the current sign of the value and its short-term trend (current vs prior snapshot).

```json
{
  "model": "signed_with_trend",
  "near_zero_threshold": 0.5
}
```

- If `|value| ≤ near_zero_threshold` → `neutral`.
- Else if `value > 0` and `value > previous_value` → `positive`.
- Else if `value < 0` and `value < previous_value` → `attention`.
- Else → `neutral`.

### 4.5 `categorical_state`

Used for non-numeric or state-machine-like indicators (e.g. `golden_cross` / `death_cross`, `bullish` / `mixed` / `bearish`).

```json
{
  "model": "categorical_state",
  "mapping": {
    "golden_cross": "positive",
    "near_cross":   "neutral",
    "death_cross":  "attention"
  }
}
```

The snapshot's `value_text` field holds the state string; the evaluator maps it to a zone.

### 4.6 `informational_only`

No zone is computed; the value is shown as-is. Used for the portfolio KPIs in v1.

```json
{
  "model": "informational_only"
}
```

---

## 5. `IndicatorSnapshot` entity

A single unified table stores all snapshots, regardless of indicator scope. This is the implementation of "una tabla única con todos los históricos por activo, indicador y fecha."

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `indicator_id` | UUID | Foreign key to `Indicator`. |
| `subject_type` | enum | `asset` \| `portfolio`. Matches the indicator's `scope`. |
| `subject_id` | UUID | If `subject_type = asset`, foreign key to `Asset`. If `subject_type = portfolio`, foreign key to `Portfolio`. (Note: subject_id is not a single FK; the implementation enforces it at the service layer.) |
| `as_of_date` | date | The date the snapshot represents (not the date it was computed). |
| `value_numeric` | NUMERIC, nullable | The numeric value, for quantitative indicators. |
| `value_text` | string, nullable | The state string, for qualitative/`categorical_state` indicators. |
| `source` | enum | `scheduled_job` \| `ai_analysis` \| `on_demand_calc` \| `manual_override`. |
| `source_ref` | string, nullable | An identifier of the source — e.g. for `ai_analysis`, the `AnalysisReport.id` from D07. |
| `created_at` | timestamp (UTC) | When the snapshot was computed and persisted. |

Constraints:
- For an indicator with `scope = asset`, `subject_type` must be `asset`.
- For an indicator with `scope = portfolio`, `subject_type` must be `portfolio`.
- For each `(indicator_id, subject_id, as_of_date)`, at most one snapshot exists. If a re-computation produces a new value for an already-snapshotted date, the existing row is **updated** (not duplicated).

Retention: all snapshots are retained indefinitely in v1. No automatic pruning.

---

## 6. Update strategies

The `update_strategy` field on each indicator dictates when new snapshots are produced.

### 6.1 `scheduled_daily`

A background job runs once per day to update all `scheduled_daily` indicators for all assets held in any non-archived holding.

- **Trigger time:** configurable globally. Default: 02:00 UTC (after major equity markets close in the Americas).
- **Configuration key:** `indicators.scheduled_job.daily_run_hour_utc` (integer 0–23). Default `2`.
- **Per-asset behavior:** the job iterates over every distinct `Asset` referenced by at least one active holding. For each, it requests the asset's historical price series from the market data layer (depth depends on the indicator — e.g. MA200 needs 200 days of prices) and invokes each indicator's calculator. A new snapshot is created with `as_of_date = job execution date (UTC)` and `source = scheduled_job`.
- **Insufficient data:** if the historical price series is too short to compute the indicator (e.g. asset added 30 days ago, MA200 needs 200 days), the indicator is **silently skipped** for that asset on that day. No snapshot is produced, no error is raised. When enough history accumulates later, the job starts producing snapshots normally.
- **Failure isolation:** an error computing one indicator for one asset must not stop the rest of the job. Errors are logged with sufficient context for diagnosis.
- **Archived holdings/portfolios:** assets that only appear in archived holdings are skipped (consistent with D02's archived-status rule).

### 6.2 `on_ai_analysis`

Used for fundamental indicators (PER, ROE, Debt/EBITDA, Revenue Growth YoY, Analyst Sentiment) in v1.

- These indicators are updated **only** when the AI analysis spec (D07) completes the processing of an uploaded financial report and the IA returns extracted metric values.
- For each indicator the analysis report touches, a snapshot is created with `as_of_date = the date of the report` (per D07), `source = ai_analysis`, and `source_ref = AnalysisReport.id`.
- If two reports for the same asset have the same date, the later one overwrites the earlier per the uniqueness rule in Section 5. This is a deliberate choice for v1; multi-report-per-date semantics is out of scope.

### 6.3 `on_demand_calculated`

Used for portfolio-level KPIs (TWR, CAGR, etc.) in v1.

- These are not stored as snapshots in the same way; they are **computed on demand** when the Dashboard is loaded. The implementation may choose to persist them periodically for historical charting, but in v1 only the latest computed value is displayed and no historical snapshots are retained for portfolio KPIs.
- This is captured by a special handling rule: indicators with `update_strategy = on_demand_calculated` may legally have zero stored snapshots. Their "current value" is calculated on the fly each time the Dashboard renders.
- This is a deliberate simplification for v1: charting historical TWR over time is a future feature, not currently in scope.

---

## 7. The "current + last 2 previous" view

The Asset Detail screen presents, per indicator, the current value and the two most recent previous values, plus the date each one corresponds to (per the mockup approved in the design phase).

### 7.1 Resolution rule

For a given asset and indicator:
1. List all snapshots for `(indicator_id, subject_type = asset, subject_id = asset.id)`, sorted by `as_of_date` descending.
2. The first row is "current"; the next two are "previous 1" and "previous 2".
3. If fewer than three snapshots exist, the missing slots are presented to the user as "no data yet" rather than as a zero or null.

### 7.2 Zone evaluation at display time

Zones (`positive` / `neutral` / `attention`) are **always** computed at display time using the indicator's **current** `threshold_config`, regardless of when the snapshot was created. Per the decision recorded for v1, historical snapshots store raw values only; zone labels are not persisted.

This means that if an indicator's thresholds change in the future (a new version of the seed file), all historical values — current and previous — are re-evaluated against the new thresholds. The numeric values themselves are unchanged.

---

## 8. Calculator registry (implementation note)

Each indicator's `calculator_code` corresponds to a Python function (in a registry: `name → function`) that knows how to compute the indicator's value for a given subject and date. The registry is checked at startup against the seed file: every indicator referenced in the seed must have a registered calculator, or startup fails (consistent with the fail-fast principle in Spec 00f).

Many indicators share calculators:
- All five fundamental indicators in v1 use a generic `pull_from_latest_ai_analysis` calculator, parameterized by the metric key the AI extracted (defined in D07).
- The technical indicators each have their own calculator (MA200 → moving average over the last 200 closing prices, RSI → standard RSI formula, etc.).

This separation lets the seed file evolve fast (new indicator using existing calculator = no code change) while preserving the discipline that new calculation logic is reviewed code.

---

## 9. Authorization

Indicator snapshots are read by users via the UI but the data is associated with shared `Asset` records, not per-user records. A user can therefore see the indicator values for any asset that appears in their own holdings (since indicators are properties of the asset itself, not of any one user's purchase). Indicator snapshots for assets that no user holds may still exist (e.g. if an asset was previously held and the user deleted it); these are kept indefinitely per Section 5.

Portfolio-level KPI snapshots (`subject_type = portfolio`) are subject to the same authorization rule as portfolios themselves (Spec 00b §5): a user only sees them for portfolios they own.

---

## 10. Out of scope for v1

- **Per-user customization of thresholds**: thresholds are global per indicator. A future iteration may allow each user to tighten or relax the bands.
- **Per-sector or per-asset-type threshold variants** (e.g. tech stocks have different "healthy PER" than utilities). All assets in v1 use the same thresholds for the same indicator.
- **Charting of historical indicator values over time** beyond the "current + last 2 previous" view.
- **Alerting based on indicator threshold crossings** (e.g. "notify me when RSI enters attention zone"). Alerts in v1 are for price levels only (D06).
- **Persistence of portfolio KPIs as historical snapshots** for trend charts; only the current values are surfaced.
- **Admin UI** to edit the catalog from the web application. The seed file + restart is the v1 mechanism.
- **Versioned snapshot of thresholds at the time of computation**, for trail-of-truth reconstruction. The current decision is that historical numeric values are re-evaluated against the current thresholds.

---

## 11. Rationale

The seed-file approach reconciles two requirements that were in tension: keeping the catalog data-driven (a stated goal since the very beginning of the project) and avoiding the cost of an admin UI in v1. The seed file is a configuration artifact (like `config.yaml` in Spec 00f) but separate, because the structure is richer and the change cadence is different — `indicators_catalog.yaml` will be edited only when introducing new indicators, while `config.yaml` may be touched more often for tuning limits.

The "evaluate zones with current thresholds" decision was made over "store the threshold version per snapshot" because the alternative implies a complex versioning system inside the catalog that is disproportionate to the project's needs. The cost is a small loss of historical fidelity (a value that was "neutral" yesterday might display as "positive" today if the bands moved), which is a clearly explainable behavior to the user and aligns with the system's broader goal of always showing the "current view of things."

The single unified `IndicatorSnapshot` table — across asset-level and portfolio-level indicators, across technical and fundamental — keeps the query layer simple and supports an extensible catalog naturally. Splitting by indicator type would multiply the schema cost every time a new indicator type is conceived, which is the opposite of the data-driven goal.

Silently skipping indicators with insufficient historical data (rather than producing partial/incorrect values, or raising an error) is the same principle that drives D04's handling of missing FX rates: explicit absence is more honest than a calculated lie.
