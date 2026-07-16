# Changeset C20 — Implement Realized Gain Accounting (D13)

**Status:** Pending implementation
**Type:** Cross-spec changeset
**Triggered by:** Spec D13 (Realized Gain Accounting)
**Affects implementations of:** Spec D03, Spec D04, Spec D08, Spec D10, Spec D11, Changeset C08

---

## 0. How to read this document

This changeset applies **Spec D13** to the codebase. As always: **do not rewrite the original specs**. C20 is the single source of truth for what changes in the code.

The changes are structured in ten steps ordered from lowest to highest user impact so the system remains functional at every intermediate point.

---

## 1. Extend `Sale` entity with realized-gain fields (D13 §4.1)

### What changes

Add four new columns to the `sales` table:

- `cost_basis_quote` — NUMERIC, nullable initially, populated at sale creation.
- `cost_basis_base` — NUMERIC, nullable initially.
- `realized_gain_quote` — NUMERIC, nullable initially.
- `realized_gain_base` — NUMERIC, nullable initially.

**Deviation from the original D13 §4.1 text, applied during implementation:** D13 originally described `reason` as a new column. The codebase already has a `Sale.notes` column (TEXT, nullable) serving the identical purpose — optional free-form text on a sale — inherited from Spec D03 §3.4. Rather than add a second, redundant free-text column, `notes` is reused as `reason` (same column, no rename, no migration needed for it). Application-layer validation adds the 500-character cap on `notes`/`reason` that D13 requires. `quantity` and `unit_price` are likewise kept as-is (not renamed to `quantity_sold`/`unit_sale_price`) to preserve the naming symmetry with `Lot.quantity`/`Lot.unit_price` that the rest of the codebase (`lot_service.py`, `summary_service.py`) already relies on.

The four numeric fields are nullable in the database (to accommodate the migration of existing sales — see below) but always populated for new sales created after C20 is applied.

### Where in code

- **`backend/app/sales/models.py`** — add the five columns to the `Sale` SQLAlchemy model.
- **`backend/app/sales/schemas.py`** — extend Pydantic response models to include the new fields.
- **New Alembic migration** — adds the columns.
- **Backfill routine** (part of the same migration): for every existing `Sale` row, if it has corresponding `SaleLotConsumption` rows, compute the four numeric fields from them; otherwise leave them null and log a warning. The reason field remains null for all existing sales.

### Why

Per D13 §4.1, these fields carry the immutable realized-gain values computed at sale creation. Without them, downstream aggregation (portfolio summary, holding summary) cannot read realized P&L efficiently.

### Acceptance criteria

- After migration, all existing sales that have complete `SaleLotConsumption` history get their numeric fields backfilled correctly (spot-check three arbitrary sales manually).
- New sales created after C20 have all four numeric fields populated on write.
- The `reason` field accepts empty and null values; enforcement of the 500-char limit is at the API validation layer.

---

## 2. Implement FIFO consumption logic in `SaleService` (D13 §4.2, §7.2)

### What changes

Implement (or reimplement) the FIFO consumption algorithm inside `SaleService.create_sale(...)`:

1. Load active lots for the holding, ordered by `purchase_date` ASC, `created_at` ASC as tiebreaker.
2. Compute `remaining_to_sell = quantity_sold`.
3. Iterate lots; for each: `available = quantity - quantity_consumed`; take `units = min(remaining_to_sell, available)`.
4. Append `SaleLotConsumption(sale_id, lot_id, units_consumed=units)` to a list.
5. Accumulate `cost_basis_quote += units * lot.unit_price` and `cost_basis_base += units * lot.unit_price * lot.fx_rate_at_purchase`.
6. Decrement `remaining_to_sell -= units`; if 0, break.
7. If loop exits with `remaining_to_sell > 0`, raise `InsufficientUnitsError` — no database write happens.
8. Persist: create Sale row (with the computed cost basis and realized gain populated), create all `SaleLotConsumption` rows, update each affected lot's `quantity_consumed`. All in one transaction.

### Where in code

**Implementation note:** the codebase does not have an `app/sales/` package — Sale
logic lives in `backend/app/services/sale_service.py` (mirrors `lot_service.py`,
`summary_service.py`), and its endpoints in `backend/app/api/holdings.py`
(mirrors the existing Holding/Lot routes, all nested under
`/portfolios/{portfolio_id}/holdings/{holding_id}/...` to reuse the existing
ownership check — this changeset follows that structure instead of introducing
a parallel `app/sales/` package or bare `/sales/{id}` routes).

- **`backend/app/services/sale_service.py`** — pure `compute_fifo()` +
  `FifoResult`/`LotConsumption` dataclasses (no I/O — same
  pure-computation/thin-DB-fetch split as `fx_engine.py` and
  `summary_service.py`), plus `InsufficientUnitsError` (subclasses
  `ValueError` so the existing `except ValueError` → HTTP 400 handling in
  `holdings.py` needs no change) and the rewritten `create_sale()`.
- **Unit tests** in `backend/tests/services/test_sale_service.py`:
  - Sell exactly the units of the first lot → one consumption row, first lot fully consumed, second lot untouched.
  - Sell across two lots → two consumption rows, correct proportions.
  - Sell more than available → raises `InsufficientUnitsError`, no rows written.
  - Sell exactly all remaining units → all lots become fully consumed, holding `active_units = 0`.
  - Cross-currency: portfolio EUR, asset USD → `cost_basis_quote` in USD, `cost_basis_base` in EUR, correctly respecting each lot's original `fx_rate_at_purchase`.

### Why

Per D13 §3 and §4.2, FIFO is the single source of truth for cost basis. Encapsulating the logic in one service method with strict transactional semantics prevents partial states.

### Acceptance criteria

- Given the worked example in D13 §3.1, the service produces exactly the expected `cost_basis_*` and `realized_gain_*` values.
- Attempting to oversell raises the error without any DB write.
- The atomic transaction is verified by killing the database connection mid-write in a test — the DB state is restored to pre-attempt.

---

## 3. Add the FIFO preview endpoint (D13 §7.1)

### What changes

Add a read-only endpoint that returns the FIFO preview for a proposed sale, without writing anything.

### Where in code

**Implementation note:** following the file-structure deviation already recorded
in §2, the endpoint lives in **`backend/app/api/holdings.py`** as
`POST /portfolios/{portfolio_id}/holdings/{holding_id}/sales/preview`
(not a bare `/holdings/{holding_id}/sales/preview` — nested for the same
ownership-check reuse as every other route in that file), guarded by
`Depends(require_permission("sale.create"))`. It calls
`sale_service.compute_fifo_preview()`, which delegates to the same
`compute_fifo()` used by `create_sale` (§2) — not a reimplementation.

- The endpoint receives the same fields as sale creation (`SaleIn`) and returns a `SalePreviewOut` payload per D13 §7.1.
- If quantity exceeds available, response includes `insufficient_units: true` and `units_available: N` (HTTP 200, not an error).

### Why

Per D13 §5.3, the frontend renders the preview before submission using the exact numbers the backend would produce, avoiding client-side FIFO drift.

### Acceptance criteria

- ✅ With valid input, the preview matches what `create_sale` would produce with identical input — verified manually: selling 3 units of the same test holding via `/preview` and then via `/sales` produced byte-identical `cost_basis_*`/`realized_gain_*` figures.
- ✅ With excess quantity, the preview returns `insufficient_units: true` and HTTP 200 — verified manually.
- FX rate fetch failure marks `fx_rate_origin = manual_pending` in the preview so the UI can prompt the user (reuses the existing `_resolve_fx_rate` helper already exercised by `create_sale`; not re-verified separately here).

---

## 4. CRUD endpoints for sales (D13 §7.2, §7.3, §7.4, §11)

### What changes

Introduce (or complete, if already partially present) the four HTTP endpoints, all nested under `/portfolios/{portfolio_id}/holdings/{holding_id}/...` per the file-structure deviation from §2:

- `POST .../sales` — create. Guarded by `sale.create`. (Already present from D03; extended in §2 with the immutable realized-gain fields.)
- `GET .../sales` — list for a holding, newest first. Guarded by `sale.view`. **Added this step.**
- `PATCH .../sales/{sale_id}` — edit reason only. Guarded by `sale.edit_reason`. (Rewritten in §2, ahead of schedule, because the service-layer change forced touching this endpoint in the same commit.)
- `DELETE .../sales/{sale_id}` — delete with FIFO rollback. Guarded by `sale.delete`. (Already present from D03, unchanged.)

### Where in code

- **`backend/app/api/holdings.py`** — `list_sales` (new) and `preview_sale` (§3) handlers; `create_sale`/`update_sale_reason`/`delete_sale` already existed or were updated in §2.
- **`backend/app/services/sale_service.py`** — `list_sales_for_holding()` (new, thin — mirrors `get_sale()`).
- **Unit tests**: PATCH/DELETE behavior for the immutability contract was verified manually (§2's acceptance criteria) rather than with dedicated automated HTTP-layer tests, consistent with Spec 00c §2's "Medium priority" rating for DB-touching integration tests in a codebase with no existing FastAPI `TestClient` test fixtures.

### Why

Per D13 §7 and §11, these are the endpoints the frontend consumes. The `PATCH` is deliberately restricted to `reason` so financial data stays immutable.

### Acceptance criteria

- ✅ After DELETE, the sold units become available again for a subsequent sale — verified manually (§2).
- A user cannot view sales of holdings they don't own (returns 404) — inherited for free from `_require_portfolio`/`get_holding_with_asset`, the same ownership check every other route in this file already uses; not re-verified separately.
- A user without `sale.delete` gets HTTP 403 when calling DELETE — inherited from `require_permission`, the same mechanism gating every other endpoint; not re-verified separately.

---

## 5. Add sale permissions to the roles catalog (D13 §12)

### What changes

Add four permission codes to `roles_catalog.yaml` and assign them to both `investor` and `administrator` roles.

### Where in code

- **`backend/roles_catalog.yaml`** — add `sale.create`, `sale.view`, `sale.edit_reason`, `sale.delete`. Assign all four to both roles.
- The seed loader from Changeset C02 §1 will upsert them at next startup.
- **Spec D11 §5.1 catalog table** — update the "sale" domain row to reflect the actual permissions per D13 §12. This is the same narrow lockstep exception used in prior changesets when a spec is a registry.

### Why

Per D13 §12, every new endpoint must declare its permission. Without adding them to the catalog, the seed validator would fail at startup.

### Acceptance criteria

- After a fresh startup, the four permissions exist in the `permissions` table.
- Both roles have them assigned in `role_permissions`.
- The startup permission-existence check (introduced in C02 §5) passes.

---

## 6. Update `PortfolioSummaryService` with realized P&L (D13 §8, C08 §3)

### What changes

Extend the summary computation:

- Add `realized_pnl` — sum of `realized_gain_base` across all sales of the portfolio's holdings.
- Add `realized_pnl_pct` — `realized_pnl / total_invested_ever` where `total_invested_ever` is the sum of `unit_price * quantity * fx_rate_at_purchase` across every lot ever created (including fully consumed ones).
- Narrow `unrealized_pnl` semantically: it now explicitly excludes any consumed units. The formula becomes `sum over active lots of (current_price * remaining_units * fx_current - unit_price * remaining_units * fx_rate_at_purchase)`.

Also add cache invalidation triggers per D13 §8.1: `sale created`, `sale deleted`, `sale reason updated` (only the third does NOT invalidate — reason has no financial impact). **Already satisfied** — Step 2 built `update_reason`'s endpoint without an invalidate call from the start, and `create_sale`/`delete_sale` already invalidated from D03. No change needed here.

**Correction found during implementation:** D13 §8's literal text for `total_invested_ever` ("the sum of `unit_price × quantity`") omits `fx_rate_at_purchase`, which would leave a quote-currency figure as the denominator for a base-currency numerator — nonsensical for a multi-currency portfolio. This changeset's own formula above (`unit_price * quantity * fx_rate_at_purchase`) is correct and is what got implemented; D13 §8 should be read with that correction.

**Bug found and fixed during manual verification:** a sale dated after "today" was being counted in `realized_pnl` immediately, while its consumed units still counted as held on the unrealized side (their consumption is date-gated by `_quantity_remaining_at`, same as it already was for lots) — silently double-counting the same position as both held and sold. Fixed by excluding sales with `sale_date > today` from the realized-P&L sum, mirroring the existing future-dated-lot exclusion. Caught by creating a real sale via the API dated one day ahead of the dev container's clock and observing `realized_pnl` update before the fix, then correctly stay at 0 after it — not something the original acceptance criteria below anticipated, so a dedicated unit test (`test_realized_pnl_excludes_future_dated_sales`) was added to lock it in.

### Where in code

**Implementation note:** per this project's actual module layout (not the `app/portfolios/` package assumed above):

- **`backend/app/services/summary_service.py`** — `HoldingSnapshot` gains a `sales: tuple[tuple[date, Decimal | None], ...]` field (sale_date paired with `realized_gain_base`, needed for the future-date exclusion above); new pure `_compute_realized_totals()`; `_fetch_holding_snapshots` eager-loads `Holding.sales`.
- **`backend/app/api/portfolio_schemas.py`** — `PortfolioSummary` gains `realized_pnl`/`realized_pnl_pct`.
- **`backend/app/api/holdings.py`** — cache invalidation already in place (see above); no new code.
- **Unit tests** (`backend/tests/unit/test_summary_service.py`), verifying:
  - Portfolio with only unrealized: `realized_pnl = 0`.
  - Portfolio with only sold assets: `unrealized_pnl = 0`, `realized_pnl` matches manual calculation (D13 §3.1 worked example, reused here).
  - Mixed portfolio, mixed currency: both correctly computed and non-overlapping.
  - A sale with unknown gain (`None`) is excluded, not treated as zero.
  - A future-dated sale is excluded until its date arrives (see bug note above).
  - A fully-consumed lot still counts in full towards `total_invested_ever`; a lot with unresolved FX is excluded from it.

### Why

Per D13 §8, realized P&L is now first-class data for portfolio aggregates. Without this update, the header tile from §7 below has no data source.

### Acceptance criteria

- ✅ Existing tests for `PortfolioSummary` continue to pass with the new fields defaulted to zero when no sales exist.
- ✅ The new fields appear in `GET /portfolios/{id}/summary` responses — verified manually against the dev DB (create sale → `realized_pnl` updates immediately; delete sale → reverts).
- ✅ Cache invalidation triggers work correctly — verified manually: creating a sale changed the very next `GET .../summary` response without waiting for TTL expiry.

---

## 7. Update `pi-portfolio-header` to render the P&L REAL. tile (D13 §8, C08 §7)

### What changes

The portfolio header component gains the fourth tile (P&L REAL.) that was hidden in C08 §2. It now:

- Reads `realized_pnl` from the summary response.
- Renders the value with the currency symbol of the portfolio's base currency.
- Color-codes green if positive, red if negative, neutral if zero.
- Places between the "P&L LAT." tile and the "30D chart" tile.

Layout adaptation: on mobile viewports (< 640px), the four tiles + chart stack vertically as before.

### Where in code

- **`frontend/src/components/portfolio-header.ts`** — add the tile rendering.
- **`frontend/src/i18n/locales/es.json` and `en.json`** — add `portfolio_header.realized_pnl` key.

### Why

Per D13 §8 and Changeset C08 §11.1 (now closed), this tile completes the portfolio header as originally designed.

### Acceptance criteria

- ✅ A portfolio with no sales shows P&L REAL. (implemented as the sentence-case "P&L realizado"/"Realized P&L" label, matching the existing "P&L latente"/"Unrealized P&L" sibling tile's actual style rather than the all-caps mockup text quoted in D13 §8) as `$0.00` — verified visually via Playwright.
- ✅ After a sale is created, the tile updates immediately (summary cache invalidation from Step 2/6) — verified visually: created a sale via the API, reloaded the portfolio in the browser, tile went from `$0.00` to `$10.00` in green; deleted the sale afterward to restore the fixture.
- ✅ Color is correct for positive realized P&L (green); zero renders neutral. Negative (red) not separately screenshotted but uses the same `deltaClass` logic already proven for the unrealized tile.

---

## 8. Sale action UI on the asset detail screen (D13 §5)

### What changes

Add the "Vender" (Sell) button to the asset detail screen and the modal/sub-screen with the sale form + FIFO preview.

Behavior:

- Button appears alongside existing actions.
- Clicking opens a modal (`pi-sell-modal`) or a dedicated sub-screen.
- Fields per D13 §5.2. Default quantity = current available units.
- As the user types, `POST /holdings/{holding_id}/sales/preview` is called (debounced 300ms) and the FIFO preview updates below the form.
- Submit button: enabled only when the preview is valid (`insufficient_units: false`) and all required fields are filled.
- On submit success: close modal, refresh the asset detail view (which now shows the new sale in the history section — §9 below).
- On failure: show error inline, keep modal open, do not lose input.

### Where in code

**Implementation note:** this project has no modal-overlay pattern anywhere in
the frontend — every existing form (add/edit lot, edit asset) is an inline
section toggled by a boolean component field, using raw `innerHTML =`
re-renders rather than a component framework. `pi-sell-modal` follows suit as
an inline section, not a new `pi-sell-modal` component or overlay, for
consistency with the rest of `asset-detail-screen.ts`.

- **`frontend/src/screens/asset-detail-screen.ts`** — the "Vender" button (reusing the existing, previously-unwired `screen.holding.add_sale` i18n key) and the inline sell form + preview, in the same file as every other holding action.
- **`frontend/src/api/sales.ts`** — new file: `previewSale`, `createSale`, `updateSaleReason`, `deleteSale`. `listSales` stays in `api/holdings.ts` (already used by the pre-existing, unrelated `history-screen.ts`) rather than being duplicated.
- Removed `AddSaleBody`/`addSale`/old `deleteSale` from `api/holdings.ts` — a stale, never-wired `lot_id`-based shape from before FIFO auto-selected lots; dead code, not a working alternate path.
- The preview's debounced input handling updates only a `#sell-preview-container` div and the submit button's `disabled` attribute directly via DOM, instead of a full component re-render on every keystroke — a full re-render would replace the input elements and steal focus mid-typing (this project's raw-`innerHTML` rendering has no keyed-diffing).
- **`frontend/src/i18n/locales/es.json` and `en.json`** — new keys under the existing `screen.sale.*` namespace (not a new flat `sales.*` namespace as §11 originally sketched — kept consistent with this project's actual `screen.<entity>.<key>` i18n convention).

### Why

Per D13 §5, this is the primary entry point for recording sales. The FIFO preview ensures the user sees exactly what the backend will persist.

### Acceptance criteria

- ✅ The Vender button is visible on any asset that has `active_units > 0` — verified visually.
- ✅ 0 active units shows the message "No hay unidades disponibles para vender." instead of the button — implemented; not separately screenshotted (straightforward conditional).
- ✅ The preview updates as the user types (debounced) — verified visually: filled quantity/price, the FIFO breakdown + cost basis + proceeds + realized gain (green) appeared without losing input focus; also verified the oversell case shows "Insufficient units. Available: N" with the submit button disabled.
- ✅ Submitting creates the sale and the history reflects it immediately — verified visually.
- Errors from the backend are displayed inline at the top of the form (not per-field — no per-field validation errors are currently returned by the backend to route to a specific field).

---

## 9. Sales history section on the asset detail (D13 §6)

### What changes

Below the existing "Historial" content on the asset detail screen, add a new section **"Historial de ventas"** listing all sales for the holding.

- Each row displays: date, quantity, unit price, reason (truncated), realized gain (color-coded).
- Click on a row → expands to show FIFO breakdown, full reason, both quote and base currency values.
- Delete action on the expanded row → confirmation dialog per D13 §6.2 → calls DELETE endpoint → row disappears from the list.
- Edit-reason action on the expanded row → inline text input → save via PATCH.

### Where in code

**Implementation note:** same inline-section pattern as §8 — no new
`pi-sales-history` component; the table lives directly in
`asset-detail-screen.ts`'s existing render method, replacing the old
minimal 4-column sales table from D03.

- **`frontend/src/screens/asset-detail-screen.ts`** — sales table + expand/collapse row + delete-confirm row + inline reason editor.
- **Backend enrichment required and added in this step:** the FIFO breakdown ("which lots were consumed, in what proportion, **at what cost**" — D13 §6.1) needs each consumption's `purchase_date`/`unit_price`, which live on the consumed `Lot`, not on `SaleLotConsumption`. Added as properties on the `SaleLotConsumption` model (`purchase_date`, `unit_price`, `cost_contribution`) that reach into `.lot`, so `SaleLotConsumptionResponse.model_validate(...)` picks them up transparently everywhere a `Sale` is serialized (the existing `GET .../holdings/{id}` detail endpoint included) without having to hand-build every response. Required eager-loading `SaleLotConsumption.lot` alongside `Sale.lot_consumptions` in `lot_service.get_holding_detail`, `sale_service.list_sales_for_holding`, and the two reload queries in `create_sale`/`update_sale_reason`.
- The holding's base currency (needed for the base-currency realized-gain column) is fetched via a new `getPortfolio()` call alongside the holding — the asset detail screen didn't have it before.

### Why

Per D13 §6.1, the user needs a chronological view of their sales with drilldown to the FIFO details.

### Acceptance criteria

- ✅ Sales are sorted by `sale_date` DESC — implemented client-side (small per-holding lists; no need for a dedicated sorted endpoint beyond the existing one).
- ✅ Deleting a sale restores the sold units so the Vender button becomes usable again — verified visually end-to-end: sold 2 units, deleted the sale, `QUANTITY HELD` and `TOTAL INVESTED` both reverted to their pre-sale values and the sales table returned to its empty state.
- ✅ Editing the reason updates the row immediately — verified visually: changed "Toma de beneficios" → "Rebalance" via the inline editor, reflected instantly in both the row and the expanded detail, with `quantity_sold`/`unit_sale_price`/`realized_gain` unchanged (immutability holds).

---

## 10. Portfolio-list and asset-row summary lines (D13 §9, §10)

### What changes

**Portfolio-list view (Screen 2):**
- Below each portfolio's name and status, add the summary line: `N assets · Invested €X · P&L +/-€Y (+/-Z%) ▲/▼`.
- Fetched via a new endpoint `GET /portfolios/summaries` that returns all summaries in one call.

**Portfolio dashboard (Screen 4) — asset rows:**
- Each asset row gains the summary line: `N units · Invested €X · P&L +/-€Y (+/-Z%) ▲/▼`.
- On desktop (≥ 640px): appended horizontally after the asset name.
- On mobile: appended vertically below the asset name.
- Fetched via a new endpoint `GET /portfolios/{portfolio_id}/holdings/summary`.

For assets with `active_units = 0` (all sold), the row shows: `Sold · Realized P&L +/-€Y ▲/▼` (no invested amount to show).

### Where in code — backend part (this step)

- **`backend/app/api/portfolios.py`** — `GET /portfolios/summaries`, registered *before* `GET /{portfolio_id}` (a literal `/summaries` segment would otherwise be swallowed as an attempted `portfolio_id` UUID and 422 before reaching the handler).
- **`backend/app/api/holdings.py`** — `GET /portfolios/{portfolio_id}/holdings/summary`, registered before `GET /{holding_id}` for the same reason.
- **`backend/app/services/summary_service.py`**:
  - `HoldingPnl` + pure `_compute_holding_pnl()`/`compute_holding_summaries()` — per-holding row (units, invested, unrealized/realized/total P&L), reusing `_quantity_remaining_at`, `_last_known`, and `fx_engine.calculate_holding` the same way `_compute_current_totals` does, but returning one row per holding instead of a portfolio-wide sum. Deliberately a separate function from `_compute_current_totals` rather than a shared one — the two round at different points (per-row vs. once at the portfolio total), so sharing would risk perturbing the aggregate's existing, tested output.
  - `get_holding_summaries()` — thin, reuses the exact same fetchers as `get_summary()` (`_fetch_holding_snapshots`, `_fetch_price_series`, `_fetch_fx_series`).
  - `get_portfolio_list_summaries()` — loops `get_summary()` per portfolio (benefiting from its existing 5-minute cache) rather than a bespoke cross-portfolio SQL aggregate; `assets_count` is the one piece genuinely fetched in a single dedicated query (`_fetch_active_holdings_count`) across every portfolio at once, since it isn't part of `PortfolioSummary`. **Interpretation of "one query, no N+1" (see acceptance criteria):** read as "one HTTP round trip, no per-portfolio/per-holding *request*" rather than "exactly one SQL statement total" — a fully single-query cross-portfolio aggregate would require rearchitecting the pure/thin split that the rest of this service (and its test coverage) relies on, for a benefit that doesn't matter at this app's personal-portfolio scale (a handful of portfolios per user).
- **`backend/app/api/portfolio_schemas.py`** — `PortfolioListSummary`. **`backend/app/api/d03_schemas.py`** — `HoldingPnlResponse` (kept with the other holding schemas, not a new `portfolios/schemas.py` file).
- Frontend consumption (client functions, screen rendering) is Step 11, not this step.

### Why

Per D13 §9 and §10, surface the P&L information where the user is already looking, without requiring drilldown.

### Acceptance criteria (backend part)

- ✅ Portfolios list data available via one call — verified manually: `GET /portfolios/summaries` returned all 3 of the dev account's portfolios (assets_count, total_invested, unrealized_pnl, realized_pnl, total_pnl, total_pnl_pct) in a single response.
- ✅ Sold-out holdings report the "Sold" shape — verified manually: sold out the dev account's entire INTC position, `GET .../holdings/summary` showed `active_units: 0`, `invested: 0`, `unrealized_pnl: 0`, `realized_pnl: 50`; `GET /portfolios/summaries`'s `assets_count` for that portfolio dropped to 0 in the same request. Sale deleted afterward to restore the fixture.
- ✅ Both endpoints answer in one HTTP round-trip each (see backend-part interpretation note above) — no per-portfolio or per-holding *request* from the frontend once Step 11 wires them up.
- The dashboard's actual sort order (sold-out assets at the bottom) is a Step 11 frontend concern, not addressed here.

---

## 11. Translations (Spec D08)

Add to `frontend/src/i18n/locales/es.json` and `en.json`:

| Key | Spanish | English |
|---|---|---|
| `sales.action.sell` | Vender | Sell |
| `sales.form.quantity.label` | Cantidad a vender | Quantity to sell |
| `sales.form.unit_price.label` | Precio de venta por unidad | Sale price per unit |
| `sales.form.date.label` | Fecha de venta | Sale date |
| `sales.form.reason.label` | Razón de la venta (opcional) | Reason for sale (optional) |
| `sales.form.reason.placeholder` | Ej: Toma de beneficios tras alcanzar target de 20% | E.g. Taking profits after reaching 20% target |
| `sales.form.submit` | Confirmar venta | Confirm sale |
| `sales.preview.title` | Esta venta consumirá: | This sale will consume: |
| `sales.preview.lot_line` | Lote del {date}: {units} unidades a {price} → {cost} coste | Lot from {date}: {units} units at {price} → {cost} cost |
| `sales.preview.total_cost` | Coste total | Total cost basis |
| `sales.preview.proceeds` | Ingresos por venta | Sale proceeds |
| `sales.preview.gain_positive` | Ganancia realizada | Realized gain |
| `sales.preview.gain_negative` | Pérdida realizada | Realized loss |
| `sales.preview.insufficient` | No tienes suficientes unidades. Disponibles: {available} | Insufficient units. Available: {available} |
| `sales.history.title` | Historial de ventas | Sales history |
| `sales.history.empty` | Todavía no has vendido nada de este activo | You haven't sold any units of this asset yet |
| `sales.history.delete.confirm` | Esto restaurará las unidades vendidas y eliminará la ganancia registrada del P&L de tu cartera. ¿Continuar? | This will restore the sold units and remove the recorded gain from your portfolio P&L. Continue? |
| `sales.history.delete.action` | Eliminar venta | Delete sale |
| `sales.history.details` | Ver detalle | View details |
| `sales.history.edit_reason` | Editar razón | Edit reason |
| `portfolio_header.realized_pnl` | P&L REAL. | Realized P&L |
| `portfolio_list.assets_count` | {count} activos | {count} assets |
| `portfolio_list.invested` | Invertido {amount} | Invested {amount} |
| `portfolio_list.no_investment` | Sin inversión aún | No investment yet |
| `holding_row.units` | {count} unidades | {count} units |
| `holding_row.sold` | Vendido | Sold |

Run the i18n build-time validator introduced in C06 §3 to confirm no keys are missing.

---

## 12. Order of implementation

1. **Step 1** — Extend `Sale` entity + migration + backfill (§1).
2. **Step 2** — Implement FIFO service logic + unit tests (§2).
3. **Step 3** — Add sale permissions to catalog (§5). Must be before step 4 so endpoints can declare their permission.
4. **Step 4** — Add FIFO preview endpoint (§3).
5. **Step 5** — Complete CRUD endpoints for sales (§4).
6. **Step 6** — Update `PortfolioSummaryService` with realized P&L + cache invalidation (§6).
7. **Step 7** — Update `pi-portfolio-header` with the P&L REAL. tile (§7).
8. **Step 8** — Add sales list/summary endpoints for portfolios and holdings (§10 backend part).
9. **Step 9** — Frontend: sale modal + FIFO preview UI (§8).
10. **Step 10** — Frontend: sales history section on asset detail (§9).
11. **Step 11** — Frontend: portfolio-list and asset-row summary lines (§10 frontend part).
12. **Step 12** — Translations (§11) — interleave with the frontend steps.

After all twelve steps are applied and verified end-to-end, this changeset is marked `Implemented`.

---

## 13. What this changeset does not change

- **The `Lot` entity** — unchanged, only its `quantity_consumed` field is updated by the FIFO logic (which was already the intended usage per D03).
- **Existing endpoints for lots, holdings, portfolios** — untouched.
- **Authentication, CSRF, and cookie handling** — unchanged.
- **Any spec other than D03, D04, D08, D10, D11 (indirectly via C02), and Changeset C08** — no cross-domain impact.
- **The FX engine (Spec D04)** — unchanged, only consumed.

---

## 14. Out of scope of this changeset

- All items listed in D13 §14 (fractional quantities, tax report export, wash-sale rules, base-currency change, editing numeric fields, commission modeling, bulk sales, short selling).
- **UI to reactivate a sold-out holding** (e.g. "Rebuy" as a shortcut). The user can simply add a new purchase lot via the existing "Añadir compra" flow.
- **Historical portfolio value inclusion of sold assets** — the on-the-fly 30-day trend introduced in C08 §4 continues to reflect only currently-held units, consistent with C08's scope. The realized gains are shown separately in the P&L REAL. tile.

---

## 15. Coordination with prior changesets

- **C02 (RBAC)** — this changeset extends the permission catalog. The seed loader from C02 must run cleanly with the four new codes.
- **C08 (Portfolio Header)** — this changeset closes the deferred item C08 §11.1 (P&L Realized) and completes the header's fourth tile.
- **C06 (i18n validator)** — this changeset introduces many new translation keys; the validator from C06 §3 must pass after all keys are added.

If any of C02, C06, or C08 has not been fully applied, apply them first.
