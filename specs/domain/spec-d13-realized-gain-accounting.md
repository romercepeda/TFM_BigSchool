# Spec D13 — Realized Gain Accounting

**Status:** Approved
**Type:** Domain capability
**References:** Spec D02 (Portfolio Management), Spec D03 (Asset Holdings, Purchase Lots & Sales), Spec D04 (FX Calculation Engine), Spec D06 (Price Levels, Alerts & Analysis History), Spec D08 (Internationalization), Spec D10 (Frontend Architecture), Spec D11 (Roles & Permissions), Changeset C08 (Portfolio Header — the deferred sibling)

---

## 1. Purpose

Enable users to record the sale of a portion or the entirety of their holdings and compute the **realized gain or loss** of each sale using **FIFO** (First In First Out) accounting, in line with Spanish tax reporting rules.

This spec closes a gap that was intentionally left open in earlier work: Spec D04 §1 and §10 explicitly deferred realized-gain accounting to a future spec because it requires FIFO logic across purchase lots — a concern out of scope for the initial MVP. Changeset C08 §11 subsequently named this future spec as **D13**. This document delivers it.

The spec also introduces the **user-facing surface** for recording sales: a "Sell" action on each asset, the sale-recording form with FIFO preview, a sales history view, and the aggregated realized P&L displayed at the portfolio level and at the holding level.

---

## 2. Terminology

Two kinds of P&L exist side by side in the system:

- **Unrealized P&L** (already introduced in Changeset C08 §3): the paper gain or loss of holdings the user still owns, computed as `current_market_value − remaining_invested`. Fluctuates daily with market prices.
- **Realized P&L** (introduced here): the confirmed gain or loss of holdings the user has already sold, computed at the moment of sale from the difference between the sale price and the cost basis of the specific lots consumed. Immutable once the sale is recorded.

The two are additive: `Total P&L = Unrealized P&L + Realized P&L`.

---

## 3. FIFO cost basis — the accounting rule

When a user sells N units of an asset, the system consumes N units from that asset's active lots in the order they were purchased (oldest first). Each unit consumed carries the `unit_price` of its originating lot. The **cost basis** of the sale is the sum of the costs of the consumed units:

```
cost_basis = Σ (units_taken_from_lot_i × unit_price_of_lot_i)
```

The **realized gain** is:

```
realized_gain = (units_sold × sale_price) − cost_basis
```

### 3.1 Worked example

The user owns:

| Lot | Purchase date | Units | Unit price | Total cost |
|---|---|---|---|---|
| L1 | 2025-03-15 | 30 | €10.00 | €300.00 |
| L2 | 2025-08-22 | 20 | €15.00 | €300.00 |

**Sale on 2026-11-10: 35 units at €20.00 per unit.**

FIFO consumption:
- From L1: 30 units × €10.00 = €300.00 cost basis, lot fully consumed.
- From L2: 5 units × €15.00 = €75.00 cost basis, lot has 15 units remaining.

- `cost_basis = €300 + €75 = €375`
- `sale_proceeds = 35 × €20 = €700`
- `realized_gain = €700 − €375 = €325`

After the sale, L1 is fully consumed (`quantity_consumed = 30`) and L2 has 15 units remaining active.

### 3.2 Why FIFO and not weighted average

Two reasons:

- **Fiscal correctness in Spain.** The Spanish tax authority (Agencia Tributaria) mandates FIFO for individual investors when computing capital gains on securities. Using weighted average would produce a number that does not match what the user would declare on Form 100 (IRPF). Since the app is aimed at personal investors managing their own portfolios, FIFO is the only defensible choice.
- **Infrastructure alignment.** Spec D03 §3.5 already introduced the `SaleLotConsumption` junction table, whose sole purpose is to record which lots each sale consumed and in what proportion. This infrastructure was built for FIFO from day one. Using weighted average now would leave `SaleLotConsumption` semantically inconsistent.

Weighted average remains available for **display only** as the "average cost per unit" summary on the holding view, but it is never used for tax-relevant computation.

---

## 4. Sale entity and the FIFO consumption chain

The `Sale` entity was declared in Spec D03 §3.4. This section defines its **realized-gain fields**, added as an evolution of the entity.

### 4.1 Extended `Sale` fields

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. Unchanged. |
| `holding_id` | UUID | Foreign key to `Holding`. Unchanged. |
| `sale_date` | date | The date the sale took place. Unchanged. |
| `quantity_sold` | NUMERIC | Total units sold in this transaction. > 0. Unchanged. |
| `unit_sale_price` | NUMERIC | Sale price per unit, in the asset's quote currency. Unchanged. |
| `fx_rate_at_sale` | NUMERIC | Rate between quote currency and portfolio base currency on `sale_date`, per D09 §7. Unchanged. |
| `fx_rate_origin` | enum | `auto` \| `manual` \| `corrected` \| `manual_pending`. Same semantics as Lot per D03 §3.3 (with the addition from Changeset C04 for `manual_pending`). Unchanged. |
| `reason` | text, nullable | A brief note explaining why the sale was made. Free-form, max 500 characters (enforced at the API layer). Optional. **Implementation note:** the `Sale` entity from D03 §3.4 already has a `notes` column serving this exact purpose (free-form optional text on a sale). C20 §1 reuses that column as `reason` rather than adding a redundant new one — no DB rename, no functional difference, just documenting that `notes` *is* `reason`. |
| `cost_basis_quote` | NUMERIC | **New field**: sum of the cost basis of consumed lots, in quote currency. Computed at sale time from `SaleLotConsumption`. Immutable after write. |
| `cost_basis_base` | NUMERIC | **New field**: same as above but converted to portfolio base currency using each lot's `fx_rate_at_purchase`. Enables the "true" realized gain in base currency, respecting each lot's original FX rate. |
| `realized_gain_quote` | NUMERIC | **New field**: `(quantity_sold × unit_sale_price) − cost_basis_quote`. In quote currency. Immutable. |
| `realized_gain_base` | NUMERIC | **New field**: `(quantity_sold × unit_sale_price × fx_rate_at_sale) − cost_basis_base`. In portfolio base currency. Immutable. |
| `created_at`, `updated_at` | timestamp | Unchanged. |

The four new numeric fields (`cost_basis_quote`, `cost_basis_base`, `realized_gain_quote`, `realized_gain_base`) are **populated at sale creation** by the service layer and **never recomputed**. Editing a sale is prohibited in v1 (see §11) — the only allowed change is deletion, which fully rolls back the `SaleLotConsumption` entries.

### 4.2 `SaleLotConsumption` (already exists per D03 §3.5)

Recapped here for completeness. When a sale is created:

- The service iterates over the active lots of the holding, oldest first (`purchase_date` ascending, tie-broken by `created_at` ascending).
- For each lot, computes `available = quantity − quantity_consumed`.
- Takes `min(remaining_to_sell, available)` from the lot.
- Creates a `SaleLotConsumption` row: `(sale_id, lot_id, units_consumed)`.
- Increments the lot's `quantity_consumed` by that amount.
- Reduces `remaining_to_sell`. Continues until `remaining_to_sell = 0`.

If at any point the loop runs out of lots before satisfying `remaining_to_sell`, the entire operation is rolled back and the sale is rejected with error `insufficient_units_to_sell`.

---

## 5. Recording a sale (user-facing flow)

The user records a sale from the asset detail screen. This section defines the flow.

### 5.1 Sale action on the asset

On the asset detail view (Screen 6 per D10), a new button **"Sell"** (Spanish: *"Vender"*) appears alongside the existing actions ("Niveles de precio", "Análisis", "Volver", "Eliminar activo"). Clicking opens a modal or dedicated sub-screen with the sale form.

### 5.2 Sale form fields

- **Quantity** — number, > 0, ≤ current available units (sum of `quantity − quantity_consumed` across active lots). Prefilled with the total available units to make "sell all" a one-click default.
- **Sale price per unit** — number, > 0, in the asset's quote currency. Currency is displayed as a static label next to the field (e.g. "USD").
- **Sale date** — date picker, defaults to today. Must be ≥ the earliest active lot's `purchase_date` (cannot sell before the oldest purchase).
- **Reason** — free-form text area, optional, max 500 characters. Placeholder: *"Ej: Toma de beneficios tras alcanzar target de 20% de ganancia."*

### 5.3 FIFO preview

Below the form fields, before submission, the UI shows a **read-only preview** of which lots will be consumed:

```
This sale will consume:
  · Lot from 2025-03-15: 30 units at €10.00 (fully consumed) → €300 cost
  · Lot from 2025-08-22:  5 units at €15.00 (15 units remain) → €75 cost

Total cost basis: €375
Sale proceeds:    €700
Realized gain:    +€325  (in green)
```

If the realized gain is negative (a loss), the value is shown in red with the sign, e.g. `Realized gain: −€120`.

If the FX conversion is needed (asset quoted in USD, portfolio in EUR), the preview shows both quote-currency and base-currency values in two columns, applying `fx_rate_at_sale` (auto-fetched per D09 §7, or manually entered if the auto-fetch failed).

The preview is computed by a **backend endpoint** (see §7.2) so that the user sees the exact numbers the system will persist — no client-side FIFO logic that could diverge.

### 5.4 Confirmation and rules

- Submitting the form triggers the actual sale creation. The service performs the FIFO consumption transactionally.
- If the sale would fully consume the last active lots of the holding, the holding remains in the portfolio with `active_units = 0`. The user can manually delete it later (see §5.5). This is a deliberate decision to preserve the historical record.
- After successful sale, the user is redirected to the asset detail view, where the new sale appears in the sales history section (§6).
- If the sale fails (insufficient units, FX unavailable, backend error), the modal stays open and shows the error message. Nothing is written to the database.

### 5.5 Holding with zero active units

A holding whose lots are all fully consumed has `active_units = 0`. In this state:

- The holding still appears in the portfolio's asset list (§9.3), with a visual marker (e.g. muted color, "0 units" label).
- The user can no longer add sales for that holding (would return `insufficient_units_to_sell`).
- The user can still see the holding's sales history and analyses.
- The user can manually delete the holding via the existing "Eliminar activo" action, which cascades per Spec D03 §9.

---

## 6. Sales history

Each holding accumulates a chronological history of sales.

### 6.1 Sales history section on the asset detail view

Below the existing "Historial" tabs (indicators, price levels, analyses), a new section **"Sales history"** (Spanish: *"Historial de ventas"*) lists all sales for the holding, sorted by `sale_date` descending. Each entry shows:

- Sale date.
- Quantity sold.
- Unit sale price (in quote currency).
- Reason (truncated to one line, tooltip for full text).
- Realized gain (in base currency, color-coded green/red).
- "View details" link.

Clicking "View details" opens a modal or expanded row with:

- Full reason (untruncated).
- FIFO breakdown: which lots were consumed, in what proportion, at what cost.
- Full numbers: cost basis (quote and base), sale proceeds, realized gain (quote and base).
- FX rate applied.

### 6.2 Deleting a sale

The user can delete a sale from the details view. Consequences:

- All `SaleLotConsumption` entries for the sale are removed.
- The affected lots' `quantity_consumed` decreases by the corresponding amounts, restoring available units.
- The sale row itself is hard-deleted (no soft-delete for sales in v1).

Deletion is intended for correcting user errors, not for tax-relevant amendments. The audit trail is minimal: no `sale_deleted_at` timestamp is retained. This is a deliberate simplification for v1; if a proper audit log is added later (Spec D11 §12 already flags this as a broader future spec), deleted sales would be preserved there.

**Warning on deletion:** the confirmation dialog explicitly states that this will restore the consumed units to their lots and remove the realized gain from portfolio KPIs. The user must confirm.

---

## 7. Backend service and endpoints

### 7.1 `SaleService.compute_fifo_preview(holding_id, quantity, unit_price, sale_date) -> FifoPreview`

Pure function (no writes). Returns a structured preview of what the sale **would** produce:

```json
{
  "lot_consumptions": [
    { "lot_id": "uuid", "purchase_date": "2025-03-15", "units_consumed": "30", "unit_price": "10.00", "cost_contribution": "300.00" },
    { "lot_id": "uuid", "purchase_date": "2025-08-22", "units_consumed": "5",  "unit_price": "15.00", "cost_contribution": "75.00" }
  ],
  "cost_basis_quote": "375.00",
  "sale_proceeds_quote": "700.00",
  "realized_gain_quote": "325.00",
  "quote_currency": "EUR",
  "cost_basis_base": "375.00",
  "sale_proceeds_base": "700.00",
  "realized_gain_base": "325.00",
  "base_currency": "EUR",
  "fx_rate_at_sale": "1.0000",
  "fx_rate_origin": "auto"
}
```

If the requested quantity exceeds available units, the response signals that with `insufficient_units: true` and shows how many are available, so the UI can display a clear error before the user submits.

Exposed as: `POST /holdings/{holding_id}/sales/preview`. Guarded by `Depends(require_permission("sale.create"))` (new permission — see §12).

### 7.2 `SaleService.create_sale(holding_id, quantity, unit_price, sale_date, reason) -> Sale`

The actual write operation. Wrapped in a single database transaction:

1. Fetch active lots of the holding, ordered oldest-first.
2. Compute FIFO consumption (identical to §7.1).
3. Fetch FX rate for `sale_date` per Spec D09 §7. If unavailable, mark `fx_rate_origin = manual_pending`.
4. Create the `Sale` row with all fields populated including `cost_basis_*` and `realized_gain_*`.
5. Create `SaleLotConsumption` rows.
6. Update each affected lot's `quantity_consumed`.
7. Commit.

If any step fails, the entire transaction rolls back.

Exposed as: `POST /holdings/{holding_id}/sales`. Guarded by `Depends(require_permission("sale.create"))`.

### 7.3 `SaleService.list_sales_for_holding(holding_id) -> list[SaleWithConsumption]`

Returns all sales for a holding with their FIFO breakdown joined in. Sorted by `sale_date` descending.

Exposed as: `GET /holdings/{holding_id}/sales`. Guarded by `Depends(require_permission("sale.view"))` (new permission — see §12).

### 7.4 `SaleService.delete_sale(sale_id) -> None`

Deletes the sale per §6.2. Wrapped in a transaction that restores each affected lot's `quantity_consumed`.

Exposed as: `DELETE /sales/{sale_id}`. Guarded by `Depends(require_permission("sale.delete"))` (new permission — see §12).

---

## 8. Impact on portfolio-level aggregates

The `PortfolioSummary` introduced in Changeset C08 §3 gains two new fields:

- **`realized_pnl`** (Decimal, in base currency): sum of `realized_gain_base` across all sales in the portfolio.
- **`realized_pnl_pct`** (Decimal): `realized_pnl / total_invested_ever`, where `total_invested_ever` is the sum of `unit_price × quantity` across every lot ever created for holdings in the portfolio (regardless of consumption).

The existing `unrealized_pnl` field is **narrowed** semantically: it now excludes any units that have been sold. In practice this was already implicit (unrealized was always about remaining units), but this spec makes it explicit.

**Portfolio header tile** (introduced in C08 §7 with the "P&L LAT." tile hidden for the "P&L REAL." tile): now that D13 delivers realized gains, the second tile can render:

- Label: *"P&L REAL."*
- Value: `realized_pnl` from the summary.
- Color: green if positive, red if negative.

The portfolio header component `pi-portfolio-header` in C08 must be updated accordingly.

### 8.1 Cache invalidation

The `PortfolioSummaryService` cache introduced in C08 §5 must be invalidated when a sale is created or deleted. The list of triggering operations grows to:

- Lot created / edited / deleted (from C08).
- Sale created / deleted (**new from D13**).
- Holding added / removed (from C08).

---

## 9. Portfolio-list view impact

Currently the Portfolios listing screen (Screen 2 per D10) shows only the portfolio name, base currency, and status ("active" / "archived"). D13 extends each row with a summary line:

```
Personal · EUR · active
25 assets · Invested €17,062 · P&L +€2,650 (+15.5%) ▲
```

- **Assets count**: number of distinct active holdings (with `active_units > 0`) in the portfolio.
- **Invested**: sum of `unit_price × remaining_quantity × fx_rate_at_purchase` across active lots (base currency). This is the **currently-invested** amount, not the historical total.
- **P&L**: `unrealized_pnl + realized_pnl`, in absolute value and percentage. Color-coded green (positive) or red (negative).

Portfolios with 0 active assets (all sold, or fresh) show `0 assets · No investment yet` without the P&L line.

The values come from the same `PortfolioSummaryService` (already introduced in C08). The service must expose an efficient list endpoint that returns the summary for **all portfolios of a user in one query**, so the list view doesn't fire one HTTP request per portfolio.

New endpoint: `GET /portfolios/summaries` — returns a list of lightweight summaries (one per portfolio the user owns), each including `assets_count`, `total_invested`, `unrealized_pnl`, `realized_pnl`, and `total_pnl_pct`.

---

## 10. Asset row summary in the portfolio dashboard

Currently the Portfolio dashboard (Screen 4 per D10) shows each asset row with symbol, name, and current price. D13 extends each row with the holding-level realized/unrealized summary:

**Layout — horizontal (viewport ≥ 640px):**

```
INTC  NASDAQ  Intel Corporation   50 units · Invested €900 · P&L +€325 (+36%) ▲
```

**Layout — vertical (viewport < 640px):**

```
INTC  NASDAQ
Intel Corporation
50 units · Invested €900
P&L +€325 (+36%) ▲
```

Where:
- **units**: current `active_units` of the holding.
- **Invested**: cost basis of the currently-held units (excluding sold units, in base currency).
- **P&L**: `unrealized_pnl + realized_pnl` for this specific holding, in base currency and percentage.

If the holding has `active_units = 0` (all sold), the summary shows only the realized P&L:

```
INTC  NASDAQ  Intel Corporation   Sold · Realized P&L +€325 ▲
```

Values computed by a new backend endpoint: `GET /portfolios/{portfolio_id}/holdings/summary` — returns one summary per holding of the portfolio.

---

## 11. Editability of sales

**Sales are immutable in v1.** Once created, only their `reason` field can be edited (a text field with no financial impact). All financial fields (`quantity_sold`, `unit_sale_price`, `sale_date`, `fx_rate_at_sale`, `cost_basis_*`, `realized_gain_*`) are locked.

The rationale: allowing edits would open a can of worms — recomputing FIFO consumptions retroactively, potentially unrolling and rerolling subsequent sales, dealing with lot state divergence. For an MVP focused on personal use, the friction of "delete and re-create the sale" is acceptable for the rare correction case.

The `updated_at` field of the `Sale` row is still updated when the reason changes, but no other field. This is a partial-update endpoint:

`PATCH /sales/{sale_id}` — body: `{ "reason": "..." }`. Guarded by `Depends(require_permission("sale.edit_reason"))` (new permission — see §12).

---

## 12. Impact on Spec D11 (Roles & Permissions)

Four new permission codes are added to `roles_catalog.yaml`:

- `sale.create` — record a new sale for a holding the user owns.
- `sale.view` — view the sales history of a holding the user owns.
- `sale.edit_reason` — edit the reason of a sale the user owns.
- `sale.delete` — delete a sale the user owns.

All four are assigned to both the `investor` and `administrator` roles per Spec D11 §5.2 (investors need full CRUD over their own sales; administrators inherit everything).

The `holding.view` permission (already existing) implicitly covers the ability to see the "Sell" button and to open the sale form UI; but the actual endpoints check `sale.*` explicitly.

---

## 13. Impact on other specs

| Other spec | Impact |
|---|---|
| **D03 §3.4** | The `Sale` entity gains four numeric fields (`cost_basis_*`, `realized_gain_*`) and one text field (`reason`). Backward-compatible migration. |
| **D03 §3.5** | `SaleLotConsumption` is now the primary mechanism for FIFO computation. Its role is elevated from "future support" to "core." |
| **D04 §1, §10** | The "realized-gain calculations out of scope" note is superseded. Spec D04 is updated implicitly by this spec's existence; the FX engine itself remains unchanged. |
| **C08 §3** | `PortfolioSummary` gains `realized_pnl` and `realized_pnl_pct`. The `pi-portfolio-header` component gains the "P&L REAL." tile. |
| **C08 §11.1** | The "P&L Realized deferred to D13" note is now closed. |
| **D10** | New user-facing surfaces: sell button, sale form, FIFO preview, sales history section, portfolio-list summary, asset-row summary. All within existing screens; no new routes. |
| **D11 §5.1** | Four new permission codes (§12). |
| **00f** | No new configuration keys. |
| **00e** | No new environment variables. |

---

## 14. Out of scope for v1

- **Sale of a lot with a partial-unit quantity** (e.g. 0.5 units). Assumed integer quantities. If fractional shares appear later (e.g. for crypto), the FIFO logic already supports Decimal arithmetic — only the input validation needs relaxing.
- **Tax report export** (PDF or CSV for filing with the Agencia Tributaria). The data is all there in `Sale` rows, but generating a formal tax report is a separate concern with legal implications.
- **Wash-sale rules** (rebuying within 60 days invalidates loss recognition per Spanish rules). Complex, and requires cross-holding lookback. Deferred.
- **Multi-currency portfolios where the user changes base currency mid-life**. The base currency is immutable per Spec D02.
- **Editing the numeric fields of a sale post-creation** (§11 restricts editing to `reason` only).
- **Amortization of buying commissions into cost basis**. Commissions are not modeled in the system; the user is expected to enter net cost prices.
- **Bulk sale operations** (selling positions across multiple holdings in one transaction). Each sale is per-holding.
- **Automatic "sell entire holding" shortcut with market price fetched live**. The user always enters the sale price manually to preserve accuracy — market prices can differ from actual execution prices in a real broker.
- **Short selling** (selling units the user does not own). Not applicable to the personal-investor use case v1 targets.

---

## 15. Rationale

The choice of FIFO over other cost-basis methods is grounded in Spanish tax law, which mandates it for individual investors. The system exists to help the user manage their portfolio and, implicitly, their tax reporting; producing gain figures that would not match the user's IRPF declaration would be a design failure.

Making sales **immutable except for the reason field** is a deliberate simplification. In an MVP, editability of financial records introduces enormous complexity — cascading recomputations of FIFO for subsequent sales, versioning of past states, reconciliation with previously reported figures. The "delete and re-create" workflow is not elegant, but it is correct and takes seconds. When the system ever needs full editability, that will be a substantial new spec with careful thought about audit trails.

Persisting **both** `realized_gain_quote` and `realized_gain_base` at sale time addresses a subtle but important accounting point: an asset held in USD by a EUR portfolio produces two conceptually distinct gains — the gain in the asset's own currency (relevant for tracking asset performance) and the gain in the investor's home currency (relevant for tax). Computing them at sale time and storing them immutably means the numbers are stable even if the historical FX rate database is later updated.

The **holding-level summary line** and the **portfolio-list summary line** were suggested by the project owner as UI-driven requirements. They surface the P&L information exactly where the user is looking (the list of portfolios, the list of assets) rather than requiring the user to click into a detail screen to see how they are doing. This is an ergonomic improvement that costs almost nothing computationally, since the data is already available via `PortfolioSummaryService`.
