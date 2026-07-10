# Changeset C15 — Indicator Last-Known-Value Fallback, Period Label, and Technical/Fundamental Grouping

**Status:** Implemented
**Type:** Cross-spec changeset (bug fix + requirement change)
**Triggered by:** Project owner reviewed the asset detail screen's indicator cards and found a fundamental indicator ("Deuda/EBITDA") showing "—" even though its own history row underneath showed a real value ("22 ene: 4,91"). Same review asked for two related UI improvements: every indicator card should visibly show which date/period its current value belongs to, and the indicator grid should be split into clearly delimited "Indicadores Técnicos" / "Indicadores Fundamentales" groups.
**Affects implementations of:** Spec D05 (Indicator Catalog & Historical Snapshots) §6.1, §7; Spec D07 (AI Report Analysis) §9.2; Changeset C05 §8; Spec D10 (frontend architecture).

---

## 0. How to read this document

This is the same class of bug as Changeset C14 (price fallback), found in a sibling data path: `IndicatorSnapshot`. Part 1 below is the bug fix (mirrors C14 exactly). Parts 2 and 3 are the two additional UI requests made in the same review, bundled into this changeset because they touch the same component (`pi-indicator-card`) and the same screen section.

---

## 1. Bug — a snapshot with no value can mask a real earlier value

### Root cause

`_write_indicator_snapshots` (`backend/app/worker/tasks.py`, D07 §9.2) upserts an `IndicatorSnapshot` row for every `on_ai_analysis` indicator present in an AI extraction's `metrics` dict — **even when the extracted value is `null`** (the AI processed the report but didn't find that particular metric disclosed in it, e.g. a company that doesn't report Debt/EBITDA in a given filing). This null-valued row becomes the newest `as_of_date` for that indicator/asset pair. `get_asset_indicator_history` (`backend/app/services/indicator_service.py`) then picks the most recent row as "current" regardless of whether it has a value, so a real value from an *earlier* report gets buried and "current" shows nothing — the exact bug reported.

This is the mirror-image gap of the one Changeset C14 fixed for prices: there, a live *fetch* could fail; here, a *stored* row can legitimately carry no information, but was still allowed to shadow a real one. `run_daily_indicators` (the `scheduled_daily` / technical path) already had the correct guard — `if value_numeric is None and value_text is None: continue` — the AI-analysis path was simply missing the equivalent line.

### What changes

- **`backend/app/worker/tasks.py`** (`_write_indicator_snapshots`): adds the same `if value_numeric is None and value_text is None: continue` guard already used by `run_daily_indicators`. Going forward, an AI report that doesn't disclose a metric no longer writes (or overwrites) a snapshot for it — a real value from an earlier report is never clobbered by a later report's silence.
- **`backend/app/services/indicator_service.py`** (`get_asset_indicator_history`): defends against the *pre-existing* null rows already in the database (written before this fix) and against any other future edge case producing a valueless row. The query now over-fetches (`_HISTORY_LOOKBACK_ROWS = 12`, instead of the previous hard `limit(3)`), filters out any snapshot where both `value_numeric` and `value_text` are `None`, and only then takes the first 3 — so "current" is always the most recent snapshot that actually has a value, exactly mirroring Changeset C14's last-known-value fallback for prices. A genuinely never-valued indicator (no snapshot has ever carried a value) still correctly shows "—" — unchanged from before.
- A useful side effect: the `signed_with_trend` zone model (used by MACD) compares each snapshot to `previous_value_numeric` — before this fix, a null row sandwiched between two real ones would silently break that comparison (`previous_value_numeric` would be `None` where it should have been the last real reading). Filtering nulls before pairing prev/current fixes that too, at no extra cost.

### Where in code

- `backend/app/worker/tasks.py` — `_write_indicator_snapshots`.
- `backend/app/services/indicator_service.py` — `get_asset_indicator_history`, new `_HISTORY_LOOKBACK_ROWS` constant.

### Acceptance criteria

- An indicator with snapshots `[null @ 2026-04-23, null @ 2026-03-28, 4.91 @ 2026-01-22]` now shows **4.91, dated 22 Jan 2026** as "current", with an empty ("no previous readings") history — verified manually against a synthetic row inserted into the local dev DB and removed after verification.
- An indicator with **no** valued snapshot at all still shows "—", no period label, no history — unchanged.
- A future AI report that doesn't disclose a given metric no longer creates a null row that could shadow an existing real value.

---

## 2. Every indicator card shows the period its current value belongs to

### What changes

Previously, `report_period_name` (Changeset C05 §8, e.g. `"FY 2025"`, `"Q1 2026"`) was only surfaced as an invisible hover `title=` attribute, and only on **history** entries — never on the current value, and never as visible text. The project owner's ask: make this visible directly under the current value for every card, not hidden behind a hover.

`pi-indicator-card` now renders a small label under the current value:
- **AI-derived (fundamental) indicators**: the `AnalysisReport.report_period_name` of the report that produced the current value (e.g. *"FY 2025"*), when set.
- **Technical / scheduled-job indicators, or a fundamental snapshot with no period name set**: the snapshot's `as_of_date`, formatted as a medium date (e.g. *"22 ene 2026"*) — this is "the date of the processing it belongs to," per the project owner's own framing.

No backend schema change was needed — `SnapshotOut.source_report_name` and `SnapshotOut.as_of_date` were already returned by `GET /assets/{asset_id}/indicators` (Changeset C05 §8); this changeset only makes the field visible in the UI instead of tooltip-only, and extends its use to the current value in addition to history.

### Where in code

`frontend/src/components/indicator-card.ts` — new `currentPeriodLabel` computed in `render()`, new `.period` CSS rule, rendered between `.unit` and the zone pill.

### Acceptance criteria

- A fundamental indicator with `report_period_name = "FY 2025"` shows "FY 2025" under its current value.
- A fundamental indicator with no `report_period_name` set, or a technical indicator, shows its `as_of_date` (e.g. "3 jul 2026") under the current value instead.
- An indicator with no current value at all (never priced/reported) shows no period label, consistent with showing "—" for the value itself.

---

## 3. Indicator grid grouped and delimited by Técnicos / Fundamentales

### What changes

The flat indicator grid on the asset detail screen is split into two visually bordered groups, using the `Indicator.nature` field the catalog already carries (`technical` | `fundamental` — `portfolio_kpi` never appears at `scope=asset`, so the split is exhaustive for this screen):

- **"Indicadores Técnicos"** — MA200, 50/200 Cross, RSI(14), MACD, Relative Volume.
- **"Indicadores Fundamentales"** — PER, ROE, Debt/EBITDA, Revenue Growth, Analyst Sentiment.

Each group renders in its own bordered/rounded container (`.indicator-group`, same visual language as the existing `.summary-card` boxes) with a small uppercase group title above its grid. A group with zero indicators (not possible today, but kept defensive for a future catalog change) simply doesn't render. The "Ver guía de indicadores" link stays once at the top of the overall "Indicadores" section header, applying to both groups.

### Where in code

- `frontend/src/screens/asset-detail-screen.ts` — `_renderDetail()` splits `this._indicators` into `technicalIndicators` / `fundamentalIndicators` and renders two `.indicator-group` blocks instead of one flat grid; `_mountIndicatorCards()` replaced by `_mountIndicatorGroup(gridId, nature)`, called once per group.
- `frontend/src/i18n/locales/es.json` / `en.json` — new keys `screen.holding.indicators_technical`, `screen.holding.indicators_fundamental`.

### Acceptance criteria

- Asset detail screen shows two clearly bordered sections under "Indicadores": Técnicos (5 cards) then Fundamentales (5 cards), matching the catalog's `nature` field.
- Each card is correctly matched to its indicator/snapshot history regardless of grouping (verified: `pi-indicator-card` values match what the un-grouped screen showed before this changeset).

---

## 4. Order of implementation

1. `backend/app/worker/tasks.py` — null-value write guard.
2. `backend/app/services/indicator_service.py` — over-fetch + filter in `get_asset_indicator_history`.
3. `frontend/src/components/indicator-card.ts` — `currentPeriodLabel` + `.period` styling.
4. `frontend/src/screens/asset-detail-screen.ts` — technical/fundamental grouping.
5. `frontend/src/i18n/locales/es.json`, `en.json` — new group title keys.
6. Manual verification (per Spec 00c §2/§3, same precedent as Changeset C14): inserted a synthetic older-dated valued snapshot for a real asset's `debt_ebitda` indicator (which only had null rows in the local dev DB) via direct SQL, confirmed via a real browser session that the card now shows that value with its date and that the two indicator groups render correctly delimited, then removed the synthetic row.
7. Deploy to Azure (no schema/migration change — `IndicatorSnapshot` is unchanged at the DB level, this changeset only changes write-time filtering and read-time selection/rendering).

---

## 5. What this changeset does not change

- The `IndicatorSnapshot` / `Indicator` schemas — no migration.
- `run_daily_indicators` (the `scheduled_daily` technical path) — already had the correct null guard; untouched.
- The zone evaluation models themselves (`evaluate_zone`) — unaffected; they already treat `None` as "no zone."
- Portfolio-level indicators (`nature=portfolio_kpi`) — out of scope, not shown on this screen.
- Any change to how `report_period_name` itself is extracted or edited (Changeset C05) — this changeset only changes where that existing field is displayed.

## 6. Out of scope of this changeset

- A backfill/cleanup migration to delete the pre-existing null `IndicatorSnapshot` rows already in the database — left in place; harmless, since §1's read-time filter already skips them permanently.
- Any change to `pull_from_latest_ai_analysis`'s calculator stub — still a no-op placeholder, unrelated to this fix (the `on_ai_analysis` update strategy never calls it; D07 writes snapshots directly).
