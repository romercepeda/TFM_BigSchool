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

- **`backend/app/sales/service.py`** — the service class.
- **`backend/app/sales/errors.py`** — declare `InsufficientUnitsError` if not already present.
- **Unit tests** in `backend/tests/sales/test_fifo.py`:
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

- **`backend/app/api/sales.py`** — new endpoint `POST /holdings/{holding_id}/sales/preview` guarded by `Depends(require_permission("sale.create"))`.
- The endpoint receives the same fields as sale creation and returns a `FifoPreview` payload per D13 §7.1.
- If quantity exceeds available, response includes `insufficient_units: true` and `units_available: N`.

### Why

Per D13 §5.3, the frontend renders the preview before submission using the exact numbers the backend would produce, avoiding client-side FIFO drift.

### Acceptance criteria

- With valid input, the preview matches what `create_sale` would produce with identical input.
- With excess quantity, the preview returns `insufficient_units: true` and no error status (HTTP 200); the UI displays it as a soft constraint, not an exception.
- FX rate fetch failure marks `fx_rate_origin = manual_pending` in the preview so the UI can prompt the user.

---

## 4. CRUD endpoints for sales (D13 §7.2, §7.3, §7.4, §11)

### What changes

Introduce (or complete, if already partially present) the four HTTP endpoints:

- `POST /holdings/{holding_id}/sales` — create. Guarded by `sale.create`.
- `GET /holdings/{holding_id}/sales` — list for a holding. Guarded by `sale.view`.
- `PATCH /sales/{sale_id}` — edit reason only. Guarded by `sale.edit_reason`.
- `DELETE /sales/{sale_id}` — delete with FIFO rollback. Guarded by `sale.delete`.

### Where in code

- **`backend/app/api/sales.py`** — the four endpoint handlers.
- **`backend/app/sales/service.py`** — `list_sales_for_holding`, `update_reason`, `delete_sale` methods.
- **Unit tests** for each:
  - PATCH with a valid reason updates only the `reason` and `updated_at`.
  - PATCH with an attempt to update `quantity_sold` returns HTTP 400 (financial fields locked per D13 §11).
  - DELETE restores lot units correctly; verify `quantity_consumed` of every affected lot returns to its pre-sale value.

### Why

Per D13 §7 and §11, these are the endpoints the frontend consumes. The `PATCH` is deliberately restricted to `reason` so financial data stays immutable.

### Acceptance criteria

- A user cannot view sales of holdings they don't own (returns 404).
- A user without `sale.delete` gets HTTP 403 when calling DELETE.
- After DELETE, the sold units become available again for a subsequent sale.

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

Also add cache invalidation triggers per D13 §8.1: `sale created`, `sale deleted`, `sale reason updated` (only the third does NOT invalidate — reason has no financial impact).

### Where in code

- **`backend/app/portfolios/summary_service.py`** — extend `get_summary` and the underlying queries.
- **`backend/app/portfolios/schemas.py`** — extend `PortfolioSummary` Pydantic model.
- **`backend/app/sales/service.py`** — call `summary_cache.invalidate(portfolio_id)` in `create_sale` and `delete_sale`.
- **Unit tests** for the new fields, verifying:
  - Portfolio with only unrealized: `realized_pnl = 0`.
  - Portfolio with only sold assets: `unrealized_pnl = 0`, `realized_pnl` matches manual calculation.
  - Mixed portfolio: both correctly computed and non-overlapping.

### Why

Per D13 §8, realized P&L is now first-class data for portfolio aggregates. Without this update, the header tile from §7 below has no data source.

### Acceptance criteria

- Existing tests for `PortfolioSummary` continue to pass with the new fields defaulted to zero when no sales exist.
- The new fields appear in `GET /portfolios/{id}/summary` responses.
- Cache invalidation triggers work correctly (verifiable by observing a `create_sale` call causes the next `get_summary` to re-query the DB).

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

- A portfolio with no sales shows P&L REAL. as `€0` (or the equivalent in the base currency).
- After a sale is created, the tile updates on the next page load (or immediately if the summary cache was invalidated).
- Color and sign are correct for both positive and negative realized P&L.

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

- **`frontend/src/components/sell-modal.ts`** — new component `pi-sell-modal`.
- **`frontend/src/screens/asset-detail-screen.ts`** — mount the Vender button and wire the modal.
- **`frontend/src/api/sales.ts`** — client functions for the four endpoints.
- **`frontend/src/i18n/locales/es.json` and `en.json`** — add UI strings per §11 below.

### Why

Per D13 §5, this is the primary entry point for recording sales. The FIFO preview ensures the user sees exactly what the backend will persist.

### Acceptance criteria

- The Vender button is visible on any asset that has `active_units > 0`.
- Attempting to open on an asset with 0 active units either hides the button or shows a message "No hay unidades disponibles para vender."
- The preview updates as the user types, with the debounce feeling smooth.
- Submitting creates the sale and the history reflects it immediately.
- Errors from the backend are displayed inline near the offending field or at the top of the modal.

---

## 9. Sales history section on the asset detail (D13 §6)

### What changes

Below the existing "Historial" content on the asset detail screen, add a new section **"Historial de ventas"** listing all sales for the holding.

- Each row displays: date, quantity, unit price, reason (truncated), realized gain (color-coded).
- Click on a row → expands to show FIFO breakdown, full reason, both quote and base currency values.
- Delete action on the expanded row → confirmation dialog per D13 §6.2 → calls DELETE endpoint → row disappears from the list.
- Edit-reason action on the expanded row → inline text input → save via PATCH.

### Where in code

- **`frontend/src/components/sales-history.ts`** — new component `pi-sales-history`.
- **`frontend/src/screens/asset-detail-screen.ts`** — mount below the existing history.

### Why

Per D13 §6.1, the user needs a chronological view of their sales with drilldown to the FIFO details.

### Acceptance criteria

- Sales are sorted by `sale_date` DESC.
- Deleting a sale restores the sold units so the Vender button becomes usable again for those units.
- Editing the reason updates the row immediately and persists across page reloads.

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

### Where in code

- **Backend:**
  - `backend/app/api/portfolios.py` — add `GET /portfolios/summaries`.
  - `backend/app/api/portfolios.py` — add `GET /portfolios/{portfolio_id}/holdings/summary`.
- **Frontend:**
  - `frontend/src/screens/portfolios-screen.ts` — render the summary line per row.
  - `frontend/src/screens/dashboard-screen.ts` — extend the asset row rendering.
  - `frontend/src/api/portfolios.ts` — add the two client functions.

### Why

Per D13 §9 and §10, surface the P&L information where the user is already looking, without requiring drilldown.

### Acceptance criteria

- Portfolios list shows the summary line for each portfolio, with correct color-coding.
- Sold-out assets appear at the bottom of the dashboard (still ordered by original criterion) with the "Sold" summary format.
- The endpoints return in one HTTP round-trip; no per-portfolio or per-holding N+1 pattern.

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
