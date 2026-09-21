# Changeset C25 — Price Level validity window ("vigencia")

**Date:** 2026-09-21
**Spec touched:** D06 (Price Levels, Alert Engine & Analysis History)
**App version:** 1.0.2.4 → 1.0.2.5

## What changed

Price Levels now carry a `valid_until` date, set at creation, alongside the existing
direction/target price/note. It answers a question the alert engine never asked before:
*did this level's condition get met on time, or only after the window I cared about had
already closed?*

- `valid_until` is **required** on every newly created level (rejected server-side if
  it's in the past). The ~10 levels that already existed before this changeset keep
  `valid_until = NULL` — treated as "no expiry defined", i.e. always counted as on-time.
  Editable while the level is still `armed`; locked once `touched`, same as
  direction/target_price (Spec D06 §3.2), so editing it can't retroactively flip how an
  already-recorded crossing is displayed.
- The crossing engine itself (`find_crossings`/`apply_crossings`) is **unchanged** — a
  level keeps being evaluated after its `valid_until` passes, so a late crossing is still
  recorded (retrospective value, per the changeset's whole point). Nothing about *whether*
  or *when* a level gets touched depends on `valid_until`.
- New derived state, computed at read time (not stored): `PriceLevel.touched_within_validity`
  — `None` while armed, `True` if touched with no `valid_until` or touched on/before it,
  `False` if touched after it.
- **Display (`set-levels-screen.ts`, the full per-holding levels list):** an armed level
  looks exactly as before regardless of whether `valid_until` has quietly passed —
  explicit product decision, no visual penalty for "hasn't happened yet." A touched level
  is shaded light green ("Triggered on time") if `touched_within_validity`, light gray
  ("Triggered — out of period") if not.
- **Alerts Panel (`price_level_service.list_portfolio_alerts`) and the asset-detail
  "Alerts" section (`asset-detail-screen.ts`):** a level touched after its `valid_until`
  is excluded from both — it no longer counts as an actionable/unread alert, only as a
  historical record in the full levels list. A level touched on time behaves exactly as
  before.

## Why

Romer wanted a way to cap how long a price target "counts" — so that a level crossed
within the window he actually cared about reads as a real hit, while one crossed months
later (after he'd already stopped watching it) doesn't inflate his sense of how often his
price calls land, but also isn't thrown away — it's still useful retrospectively, just
not as an active alert demanding attention.

## Key files

- `backend/app/db/models/price_level.py` — `valid_until` column (nullable) on
  `PriceLevel` and `PriceLevelHistoryEntry`; `touched_within_validity` property.
- `backend/migrations/versions/20260921_881378450e4e_add_valid_until_to_price_levels.py`
- `backend/app/services/price_level_service.py` — creation validation, edit restriction,
  history snapshot, Alerts Panel filtering.
- `backend/app/api/d06_schemas.py`, `backend/app/api/price_levels.py` — request/response
  schema + routing.
- `frontend/src/components/price-level-form.ts` — required date input (native `min` =
  today, plus client-side `notPastDate` validator).
- `frontend/src/screens/set-levels-screen.ts` — green/gray shading, valid-until label.
- `frontend/src/screens/asset-detail-screen.ts` — excludes expired-touched levels from
  the actionable Alerts section.

## Verification

266/266 existing backend unit tests pass unmodified (no dedicated price-level-service
unit test file exists in this codebase yet — pre-existing gap, not introduced here).
TS typecheck clean; i18n validator passed (337 keys, both locales in sync). Verified live
via Playwright against the local-production stack: created a level with a future
`valid_until`, confirmed it displays correctly; simulated a late touch (`touched_at_close_date`
past `valid_until`) and confirmed the gray "out of period" shading in the levels list and
its absence from the asset-detail Alerts section; confirmed a pre-existing touched level
(no `valid_until`) still shows green "on time" and still appears in Alerts, unchanged.
