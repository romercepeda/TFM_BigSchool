# Changeset C23 — "Total Gain" tile on the asset detail screen (D15 amendment)

**Status:** Implemented (local only — not deployed to Azure)
**Type:** Frontend-only changeset
**Triggered by:** User feedback, immediately after testing C22 locally

---

## 1. What changed

The project owner's C22 feedback session left one gap: "P&L Total" (C22) was added to the **portfolio header**, and the per-holding combined figure already existed in the **dashboard/portfolios-list rows** (C21, via `HoldingPnl.total_pnl`), but the **asset detail screen itself** — where the user actually records dividend payments — still only showed "Unrealized P&L" (price-only, computed client-side from the live current price). Recording a payment there had no visible combined-gain effect on that same page, which is exactly the gap the project owner flagged ("aun no veo la ganancia que estoy teniendo por el valor actual de la acción + el dividendo cobrado").

- `asset-detail-screen.ts`'s summary grid gains a **"Total gain"** tile, right after "Unrealized P&L": `unrealized_pl + dividends collected on this holding`. Computed entirely client-side from data the screen already has loaded (`this._currentPrice`, the holding's aggregates, and `this._dividendPayments` — no new API call).
- Uses `gross_amount_quote` (not `_base`), matching every other figure already shown on this screen (quote currency, not base currency) — this screen has never dealt in base currency at all (unlike the portfolio header/dashboard, which are base-currency views).
- Filters out any dividend payment dated after today, mirroring the same future-date exclusion rule used everywhere else in D15/D13.
- Shows a sub-line ("includes $X.XX in dividends") only when there's a nonzero dividend contribution, so the tile is silent/uncluttered for assets that haven't paid anything yet.
- New i18n keys: `screen.asset.total_gain`, `screen.asset.total_gain.includes_dividends`.

## 2. Why client-side, not a new backend field

`HoldingDetailResponse` (the endpoint this screen calls) already carries `dividend_coverage_years` (C21) but deliberately does **not** carry a live "current price" or a live unrealized-P&L figure — that has always been this screen's own responsibility, fetched separately via the cache-only `/market-data/assets/{ticker}/price` endpoint (Changeset C19) and computed in the render method (`pl = marketValue - costBasis`, pre-existing since before D15). Adding the dividend sum to that same client-side computation is the smallest change consistent with how this screen already works — a backend field would either duplicate that live-price logic server-side (which C19 specifically decided *not* to do on every page load) or require yet another round trip.

## 3. Verification

Playwright, same INTC fixture: before recording a payment, "Total gain" read `+451.20 (+451.20%)`, identical to "Unrealized P&L" (no dividends yet). After recording a $12.50 payment: `+463.70 (+463.70%)`, with "includes $12.50 in dividends" — matching the exact figure independently verified twice already in C21/C22 via the portfolio-header and dashboard-row paths. Deleted the test payment afterward; confirmed zero leftover `dividend_payments` rows for INTC in the dev DB.

TypeScript typecheck and i18n validator (331 keys) both clean. No backend changes in this changeset.

## 4. App version

`1.0.2.2` (C22) → **`1.0.2.3`**, per [[feedback-app-versioning]].
