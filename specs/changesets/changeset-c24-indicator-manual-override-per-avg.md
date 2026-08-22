# Changeset C24 — PER rename, admin manual override, trailing 3-year average (D05 amendment)

**Status:** Implemented (local only — not deployed to Azure)
**Type:** Cross-spec changeset
**Triggered by:** User feedback/request, same day as C21–C23
**Affects implementations of:** Spec D05, Spec D11 (Roles & Permissions)

---

## 0. How to read this document

Three related requests against the existing Indicator Catalog (Spec D05), amending it in place rather than a new domain spec — same convention as C21–C23 amended D15.

---

## 1. Rename "P/E Ratio" to "PER" (English locale)

Spanish already said "PER" in both `backend/i18n/es.json` and `frontend/src/i18n/locales/es.json` (`indicator.per.name`) — only the English bundles said "P/E Ratio". Changed both English bundles (`backend/i18n/en.json`, `frontend/src/i18n/locales/en.json`) to `"PER"` too, so the label is consistent regardless of UI language.

---

## 2. Admin-only manual value override (any asset-level indicator)

### What changed

`IndicatorSnapshot.source = 'manual_override'` existed only as a DB enum value since the original D05 migration — never wired to any endpoint, service function, or UI. This changeset implements it:

- **`backend/roles_catalog.yaml`** — new permission `indicator.manual_override`, added only to `administrator`'s permission list (not `investor`) — same "global, no per-user ownership scope" reasoning already used for `system.run_jobs`.
- **`backend/app/services/indicator_service.py`** — `set_manual_value()`: upserts an `IndicatorSnapshot` via the exact same `(indicator_id, subject_id, as_of_date)` ON CONFLICT DO UPDATE pattern already used by `run_daily_indicators` (scheduled_job) and the AI-analysis worker (ai_analysis) — a manual entry is simply a third writer of the same table, `source='manual_override'`.
- **`backend/app/api/d05_schemas.py`** — new `ManualIndicatorValueIn` (`as_of_date`, `value_numeric` or `value_text`).
- **`backend/app/api/indicators.py`** — new `PUT /assets/{asset_id}/indicators/{indicator_id}/manual-value`, gated by `require_permission("indicator.manual_override")`. Validates the submitted field matches the indicator's `data_type` (400 if not). No per-user ownership check — Asset is shared reference data and this is a global admin action, mirroring `PATCH /assets/{id}`.
- **Frontend** — `frontend/src/components/indicator-card.ts` gains an edit affordance (✎), visible only when `hasPermission('indicator.manual_override')` **and** the card has an `assetId` (portfolio-scoped indicators aren't supported by this endpoint — see §4). Clicking opens an inline date + value form (this project's established no-modal pattern). On save, the card dispatches a bubbling `indicator-updated` custom event; `asset-detail-screen.ts` listens for it once (guarded by `_indicatorListenerBound` so `afterRender()` — called on every re-render — doesn't stack duplicate listeners on the persistent `this.shadow`) and re-fetches indicators+histories. A `(manual)` badge is shown next to the current value whenever its `source === 'manual_override'`, visible to every user (not just admins) for transparency.

### "Gets overwritten by a future analysis" — how it actually works

No special tracking was added for this. "Current value" was already, and remains, "the snapshot with the latest `as_of_date` that has a non-null value" (`get_asset_indicator_history`, unchanged). A manual entry naturally stops being "current" once a `scheduled_job`/`ai_analysis` snapshot exists at the same or a later `as_of_date`. **Known, accepted limitation:** if a document analyzed *after* the manual entry has an *older* `report_date` than the manual entry's `as_of_date` (e.g., manually entering PER today, then next month analyzing a report dated last quarter), the manual value keeps winning until a same-or-newer-dated snapshot arrives — not automatically overwritten by report recency. Documented rather than solved, consistent with D05 §6.2's own accepted same-date-collision limitation.

---

## 3. Trailing 3-year average

### What changed

- **`backend/app/services/indicator_service.py`** — `compute_trailing_average(db, asset_id, indicator, years=3)`: a plain `AVG(value_numeric)` over every valued snapshot (any source — scheduled_job, ai_analysis, *and* manual_override all count, since backfilling historical values manually is exactly what §2 exists for) with `as_of_date` in `[today − 3y, today]`.
- **`backend/app/api/d05_schemas.py` / `indicators.py`** — `IndicatorSnapshotHistoryOut.avg_3y`, computed in `GET /assets/{asset_id}/indicators` for quantitative indicators only (a categorical state has no average).
- **Frontend** — `IndicatorSnapshotHistory.avg_3y` (new field); `indicator-card.ts` renders it as a small "3-year average: X" line, **only for `nature === 'fundamental'`** — a deliberate display-layer scope decision (the backend computes it for any quantitative indicator, cheap either way, but a multi-year average of a daily-computed technical indicator like RSI isn't a meaningful comparison the way it is for PER/ROE/etc., so the UI doesn't surface it there).

---

## 4. Scope decision: asset-level indicators only, not portfolio KPIs

Both §2 and §3 are implemented for `scope='asset'` indicators only. Portfolio KPI indicators (TWR, CAGR, max drawdown, volatility, Sharpe) are `on_demand_calculated` and, per D05 §10, never persist a snapshot in v1 at all (`calc_portfolio_*` are still no-op stubs) — the stated pain point ("the document doesn't disclose it, but I know the value") is specific to document-derived asset fundamentals, not portfolio-level computed metrics, so extending manual override to a scope that has never stored a value before was treated as a materially larger, separate change and left out of this changeset's scope.

---

## 5. Verification

Backend restarted cleanly: roles catalog seeded **47 permissions** (46 → 47), permission coverage check passed for **75 routes** (74 → 75) — confirms the new endpoint's single `require_permission` dependency resolves against a catalog-registered code. No new DB migration was needed (`manual_override` already existed in the `source` enum since D05's original migration). TypeScript typecheck clean; i18n validator clean (335 keys, up from 331).

Full Playwright walkthrough (admin login, manual value entry, badge, avg-3y display) was in progress when this changeset was committed — flagged here rather than silently claimed as done; follow up before Azure deployment.

---

## 6. App version

`1.0.2.3` (C23) → **`1.0.2.4`**, per [[feedback-app-versioning]].
