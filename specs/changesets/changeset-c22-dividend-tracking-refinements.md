# Changeset C22 — Dividend Tracking Refinements (D15 amendments)

**Status:** Implemented (local only — not deployed to Azure)
**Type:** Cross-spec changeset
**Triggered by:** User feedback on Changeset C21, received immediately after C21 was pushed
**Affects implementations of:** Spec D15, Changeset C21, Changeset C08

---

## 0. How to read this document

Two corrections requested by the project owner right after testing C21 locally. Both are additive to D15/C21, not reversals. D15 itself was amended in place (§3.1, §7.1) with short pointers to this changeset, per the project's existing convention for post-hoc corrections (e.g. D13 §8 / C20 §6).

---

## 1. `amount_type`: nominal or percentage (D15 §3.1)

### What changed

Companies announce dividends two ways: a fixed currency amount ("$0.25/share") or a percentage of the share price ("2% dividend"). The user wants to record the figure exactly as announced, not do the conversion by hand.

- `AssetDividendSchedule` gains `amount_type: 'nominal' | 'percentage'` (default `nominal`). New migration `backend/migrations/versions/20260717_3ac843934e46_add_amount_type_to_asset_dividend_.py`.
- `dividend_service.compute_dividend_coverage_years()` gains an optional `current_price_quote` parameter. When `amount_type='percentage'`, the declared percentage is converted to a nominal per-share amount (`current_price_quote * amount_per_payment / 100`) before annualizing; `None` if no current price is available (same "no invented values" principle as every other edge case in D15 §4.3).
- `summary_service.get_last_known_price()` (new, public) — cache-only price lookup mirroring `get_last_known_fx_rate()` from C21, so the conversion never triggers a live provider call (Changeset C19's rule).
- `holdings.py::_compute_dividend_coverage()` and `summary_service._compute_holding_pnl()` both now fetch/pass the current price through to the coverage calculation.
- Frontend: schedule form gains an "Amount type" select (Nominal / Percentage); the amount field's displayed unit flips between the quote currency and `%` accordingly; the schedule summary view formats the stored value the same way.

**Deviation found during implementation:** the migration needed a manual fix. `op.add_column` (unlike `op.create_table`) does **not** auto-create the Postgres enum type for a new column — it has to be created explicitly first (`_amount_type_enum.create(op.get_bind(), checkfirst=True)`) or the `ALTER TABLE` fails with `UndefinedObject`. This is the mirror-image of the `create_type=False` fix C21 needed for a *shared* enum; here the enum is brand new (not shared with any other table) but added via `add_column` instead of `create_table`, which has different auto-creation behavior in Alembic.

### Acceptance criteria
- ✅ Declared a schedule as 2% annual (current price $110.24) → "Dividend coverage" showed **9.07 years** (`20 / (110.24 × 0.02)`), matching the pure-function unit test exactly. Verified via Playwright.
- ✅ `test_percentage_type_converts_using_current_price`, `test_percentage_type_none_without_current_price`, `test_percentage_type_none_when_current_price_zero` (new, `test_dividend_service.py`).

---

## 2. "P&L Total" header tile (D15 §7.1)

### What changed

The project owner noted that recording a dividend payment didn't visibly change "P&L Latente" — correct by design (D13/C08 already defined it as paper price gain only, and D15 deliberately didn't touch that definition), but there was no header-level figure showing the *combined* result either. The dashboard/list rows already did (C21 §8/§9 of the D15 spec, via `total_pnl`), but the header component (`pi-portfolio-header`) had never had a combined figure of its own — it showed each component (Latente/Real/Dividendos) separately with no sum.

- `PortfolioSummary` (backend schema) gains `total_pnl`/`total_pnl_pct` — `unrealized_pnl + realized_pnl + dividend_income`, against `total_invested`. Computed in `summary_service.compute_summary()`.
- `get_portfolio_list_summaries()` simplified to reuse `summary.total_pnl`/`total_pnl_pct` directly instead of recomputing the same formula a second time — removes a duplication that risked drifting.
- `portfolio-header.ts` gains a sixth tile, "P&L Total" / "Total P&L", after "Dividendos" and before the 30-day chart. Color-coded green/red/neutral like the other P&L tiles.
- **`unrealized_pnl` / "P&L Latente" itself is unchanged** — explicitly not redefined, per the project owner's own choice between the two options presented.

### Acceptance criteria
- ✅ Header shows six tiles: Total Value, Invested, Unrealized P&L, Realized P&L, Dividends, **Total P&L**, plus the chart tile. Verified via Playwright.
- ✅ With only unrealized gain present (no sales, no dividends yet), "Total P&L" correctly equals "Unrealized P&L" ($451.20). `test_portfolio_total_pnl_sums_all_three_components` (new, `test_summary_service.py`) exercises the mixed case (sale + dividend + remaining position) end to end: unrealized 80, realized 30, dividends 15 → total 125, pct 0.1562 against invested 800 (verified the exact `ROUND_HALF_EVEN` halfway-case result by running the test, not by hand — 125/800 = 0.15625 exactly, rounds to the even neighbor 0.1562).

---

## 3. Tests and verification

- Backend: **268/268 tests pass** (264 from C21 + 4 new: 3 percentage-conversion tests, 1 total_pnl test).
- Frontend: TypeScript typecheck clean; i18n validator clean (329 keys, up from 325).
- Playwright: declared a percentage-type schedule on the same INTC fixture, confirmed the coverage indicator and the new header tile, then cleaned up (deleted the test schedule) — fixture confirmed back to its exact pristine state afterward, this time with a properly-scoped delete-button selector (the C21 cleanup incident is not repeated).

---

## 4. What this changeset does not change

- `unrealized_pnl` ("P&L Latente") semantics — explicitly left as-is per the project owner's choice.
- `AssetDividendSchedule`'s single-current-row design, `DividendPayment`'s immutability, the `DateAlert` reuse — all untouched from C21.
- No deployment to Azure — same local-only scope as C21.

---

## 5. App version

`1.0.2.1` (C21) → **`1.0.2.2`** on this changeset's commit, per [[feedback-app-versioning]].
