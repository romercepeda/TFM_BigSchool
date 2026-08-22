# Changeset C21 — Implement Dividend Tracking (D15)

**Status:** Implemented (local only — not deployed to Azure)
**Type:** Cross-spec changeset
**Triggered by:** Spec D15 (Dividend Tracking)
**Affects implementations of:** Spec D03, Spec D04, Spec D06/C17, Spec D09, Spec D11, Spec D13/C20, Changeset C08

---

## 0. How to read this document

This changeset applies **Spec D15** to the codebase. C21 is the single source of truth for what actually changed; D15 stays the conceptual reference. Implemented in one session end-to-end (backend → frontend → Playwright verification), following D15 §15's suggested order.

---

## 1. Data model — `AssetDividendSchedule` + `DividendPayment`

Two new tables, per D15 §3:

- `backend/app/db/models/dividend.py` — `AssetDividendSchedule` (asset-scoped, unique FK on `asset_id`, single current-state row, no history table) and `DividendPayment` (holding-scoped, mirrors `Sale`'s FX-resolution shape: `gross_amount_quote`, `fx_rate_at_payment`, `fx_rate_origin`, `gross_amount_base` computed once at creation).
- `Asset.dividend_schedule` and `Holding.dividend_payments` relationships added (`backend/app/db/models/asset.py`, `holding.py`).
- Registered in `backend/app/db/models/__init__.py`.
- Migration: `backend/migrations/versions/20260717_279c4995d04e_add_dividend_tracking_asset_dividend_.py`.

**Deviation found during implementation:** `DividendPayment.fx_rate_origin` reuses the existing `fx_rate_origin_enum` Postgres type (shared with `Lot`/`Sale`, defined in `lot.py`). This is the first time in the project a Postgres ENUM type is reused by a table created in a *separate* migration from the one that first defined it — Alembic's autogenerate naively re-emitted `CREATE TYPE fx_rate_origin_enum`, which failed with `DuplicateObject` on `db.ps1 upgrade`. Fixed by hand-editing the generated migration to use `postgresql.ENUM(..., create_type=False)` for that one column, with a comment explaining why. No prior migration in this codebase needed this pattern since D03 was the only place the enum previously existed, all in one migration.

### Acceptance criteria
- ✅ `.\scripts\db.ps1 generate` produced only the two new tables + indexes, no unrelated drift.
- ✅ `.\scripts\db.ps1 upgrade` applies cleanly after the `create_type=False` fix.
- ✅ Backend starts cleanly: roles catalog seeded 46 permissions (40 → 46), permission coverage check passed for 74 routes (67 → 74).

---

## 2. Permissions (D15 §14)

Six new codes added to `backend/roles_catalog.yaml`, assigned to both `investor` and `administrator`: `dividend.schedule.view`, `dividend.schedule.edit`, `dividend.payment.view`, `dividend.payment.create`, `dividend.payment.edit_notes`, `dividend.payment.delete`.

No `permission.dividend.*.name/description` i18n keys were added — following the existing precedent that these backend-only display keys are not yet populated for *any* permission in `backend/i18n/*.json` (checked: `permission.sale.*` etc. don't exist there either), so this isn't a regression, just consistency with what's already unfinished elsewhere.

---

## 3. Backend services (D15 §8)

- **`backend/app/services/dividend_service.py`** (new) — `compute_dividend_coverage_years()` (pure, D15 §4), `AssetDividendSchedule` CRUD (`get_schedule`, `get_schedules_for_assets` batch fetch, `upsert_schedule`, `delete_schedule`), the `DateAlert` marker-prefix fan-out (`fan_out_schedule_alert`, `remove_dividend_alert` — D15 §5.3/§5.4, reusing `DateAlert` with zero schema changes as instructed), and `DividendPayment` CRUD (`create_payment`, `update_notes`, `delete_payment`, `list_payments_for_holding`, `get_active_units`).
- **`backend/app/api/dividend_schemas.py`** (new) — Pydantic request/response shapes.
- **`backend/app/api/dividends.py`** (new) — two routers:
  - `GET/PUT/DELETE /assets/{asset_id}/dividend-schedule` (asset-scoped, no portfolio-ownership check — same shared-data model as `PATCH /assets/{id}`, per D15 §8.1).
  - `GET/POST /portfolios/{pid}/holdings/{hid}/dividend-payments`, `PATCH/DELETE .../dividend-payments/{id}` (holding-scoped, reuses `_resolve_fx_rate` imported from `holdings.py`).
- Both routers registered in `backend/app/main.py`.

---

## 4. `dividend_income` — the third P&L component (D15 §7)

Extends `backend/app/services/summary_service.py`:

- `HoldingSnapshot` gains `dividend_payments: tuple[(date, Decimal | None), ...]`, populated by `_fetch_holding_snapshots` (new `selectinload(Holding.dividend_payments)`).
- New pure `_compute_dividend_income()` — same future-date exclusion rule already proven necessary for `realized_pnl` in C20 §6 (a payment dated after "today" doesn't count yet), applied proactively here rather than waiting to rediscover the same bug.
- `PortfolioSummary.dividend_income` (new field, `backend/app/api/portfolio_schemas.py`), included in `compute_summary()`.
- `HoldingPnl.dividend_income` (new field, `d03_schemas.py`'s `HoldingPnlResponse` mirrors it) — computed per holding in `_compute_holding_pnl()`.
- Every existing `total_pnl = unrealized_pnl + realized_pnl` site now reads `+ dividend_income`: `_compute_holding_pnl()` and `get_portfolio_list_summaries()`'s `total_pnl` line.
- `PortfolioListSummary.dividend_income` added.
- Cache invalidation: `dividend_service.create_payment`/`delete_payment` endpoints call `summary_cache.invalidate(portfolio_id)`, same as sale create/delete. Schedule create/edit/delete does **not** invalidate — a schedule has no P&L effect, only the coverage indicator and alerts (matches D15 §7's explicit rule).

---

## 5. `dividend_coverage_years` indicator (D15 §4)

- Pure formula lives in `dividend_service.compute_dividend_coverage_years()`.
- `summary_service.get_last_known_fx_rate()` (new, public) — cache-only FX lookup (no live provider call, per Changeset C19's established "GET must not fetch live" rule), reusing the module's existing `_fetch_fx_series`/`_last_known` pattern.
- Wired into `HoldingPnl` (list rows, via `_compute_holding_pnl` deriving `avg_purchase_price_base = invested / active_units` — no second lot-level pass needed) and into `HoldingDetailResponse` (single-holding GET, via a new `holdings.py::_compute_dividend_coverage()` helper).
- `HoldingDetailResponse` and `HoldingPnlResponse` both gain `dividend_coverage_years: Decimal | None`.

---

## 6. Alert fan-out and sold-out cleanup (D15 §5.3, §5.4)

- `dividends.py::upsert_dividend_schedule`/`delete_dividend_schedule` call `dividend_service.fan_out_schedule_alert()` after commit — finds every active holding of the asset (across all users/portfolios, mirroring D06's asset→holdings fan-out shape) and upserts/removes a `DateAlert` matched by a `"Dividendo: {ticker}"` description-prefix marker. Zero changes to `DateAlert`'s model or its existing CRUD service, per explicit instruction.
- `holdings.py::create_sale` — after a sale reduces `active_units` to 0, calls `dividend_service.remove_dividend_alert()` so a stale reminder doesn't linger on shares no longer owned (D15 §5.4).

---

## 7. Backend tests

- `backend/tests/unit/test_dividend_service.py` (new, 9 tests) — `compute_dividend_coverage_years()`: the D15 §4.2 worked example (avg cost €8, annual €1 → 8 years), quarterly/monthly annualization, cross-currency FX application, and every `None` edge case from D15 §4.3 (no schedule, irregular frequency, zero avg cost, zero annualized dividend, unresolved FX).
- `backend/tests/unit/test_summary_service.py` (extended, +6 tests) — `dividend_income` aggregation (sum, exclude unknown/future-dated, cross-holding), and `dividend_coverage_years` wired into `compute_holding_summaries` (worked example + no-schedule case). `_holding()` test helper gained a `dividends` parameter.
- **Result: 264/264 backend tests pass** (249 pre-existing + 15 new), full suite re-run clean.

---

## 8. Frontend

- **`frontend/src/api/types.ts`** — `DividendSchedule`, `DividendPayment`, `DividendFrequency` interfaces; `dividend_income` added to `PortfolioSummary`/`PortfolioListSummary`/`HoldingPnl`; `dividend_coverage_years` added to `HoldingPnl`/`Holding`.
- **`frontend/src/api/dividends.ts`** (new) — client functions for both routers (`getDividendSchedule`, `upsertDividendSchedule`, `deleteDividendSchedule`, `listDividendPayments`, `createDividendPayment`, `updateDividendPaymentNotes`, `deleteDividendPayment`).
- **`frontend/src/screens/asset-detail-screen.ts`** — new "Dividend" section (schedule summary/form + payment history/form), inline-toggled sections following this project's established no-modal, no-framework convention (same pattern as the D13 sell form). New "Dividend coverage" summary card next to "AVG Cost". Both fetched in the same `Promise.allSettled` batch as indicators/price/alerts on load (a missing schedule 404s gracefully into `null`, not an error state).
- **`frontend/src/components/portfolio-header.ts`** — new "Dividends" tile between "Realized P&L" and the 30-day chart.
- **`frontend/src/screens/portfolios-screen.ts`** and **`frontend/src/components/asset-row.ts`** — **no code changes needed.** Both already read `total_pnl`/`total_pnl_pct` directly off the backend response rather than recomputing it client-side, so the three-term total flows through automatically once the backend serializes it (verified via Playwright — see §9).
- **`frontend/src/i18n/locales/es.json` / `en.json`** — `portfolio_header.dividend_income` plus 23 new `screen.dividend.*` keys (schedule, frequency labels, payment form/history). i18n validator passes: 325 static keys checked, both locales in parity.
- **TypeScript typecheck (`npx tsc --noEmit`): clean, no errors.**

---

## 9. Manual verification (Playwright)

Screenshots: `verification-screenshots/spec-d15-dividend-tracking/` (gitignored).

Flow driven end-to-end against the standing `playwright@verify.com` / TestPort / INTC fixture:

1. Asset detail before any dividend data: "Dividend coverage" reads `—`, Dividend section shows the empty state.
2. Declared a schedule (Quarterly, $0.25/unit, next payment +1 month, a note) → "Dividend coverage" immediately updated to **20.00 years** (avg cost $20 ÷ annualized $1.00 = 20 — matches the pure-function unit test exactly).
3. Recorded a payment ($12.50, today, a note) → appeared in Payment History immediately.
4. Navigated back to the portfolio: header's new "Dividends" tile showed **$12.50**; the INTC dashboard row updated from `+$451.20 (+451.20%)` to **`+$463.70 (+463.70%)`** — 451.20 (unrealized) + 12.50 (dividend), confirming the three-term total flows through the *existing*, unmodified `asset-row.ts`/`portfolios-screen.ts` code exactly as predicted in §8.
5. Edited the payment's reason, deleted the payment (confirm dialog), deleted the schedule (confirm dialog) — all worked, no console errors.
6. Zero `pageerror` events throughout; one benign `404` on first load (`GET .../dividend-schedule` for an asset with no schedule yet — expected, handled gracefully per §8).

**Incident during verification, self-corrected:** a cleanup script used an overly broad selector (`table >> button:has-text("Delete")`) that matched the *Purchase Lots* table (the first table on the page) instead of the intended *Payment History* table, deleting the fixture's only lot. Caught immediately from the resulting screenshot (`QUANTITY HELD` dropped to 0), and fixed by re-adding the identical lot (5 units @ $20.00, 2026-01-01) and re-running the payment deletion with a properly scoped selector. Final screenshot confirms the fixture account is back to its exact original pristine state (1 lot, 0 sales, 0 dividend data). This was a test-script bug, not an application bug — flagged here for transparency since it touched the shared verification fixture.

---

## 10. What this changeset does not change

- `DateAlert`'s model, schema, or CRUD service — untouched, reused as-is per explicit instruction.
- `Sale`/`Lot`/FIFO logic (D13/D03) — untouched, only consumed (`_resolve_fx_rate` imported, not modified).
- No automatic/provider-fetched dividend data — confirmed infeasible on this project's current provider tiers, per D15 §9's research; `AssetDividendSchedule.origin` stays `manual`-only.
- No deployment to Azure — explicitly out of scope for this round per the project owner's instruction. Local Docker + local Postgres only.

---

## 11. Out of scope

All items already listed in D15 §12 (automatic fetch, withholding tax, per-share breakdown, schedule history, auto-rolling `next_payment_date`, DRIP modeling, special-dividend distinction, non-quote-currency amounts).

---

## 12. App version

Per this project's versioning convention: `1.0.2.0` (bumped when D15 was drafted) → **`1.0.2.1`** on this changeset's commit, per [[feedback-app-versioning]].
