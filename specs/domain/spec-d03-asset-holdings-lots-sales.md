# Spec D03 — Asset Holdings, Purchase Lots & Sales

**Status:** Approved
**Type:** Domain capability
**References:** Spec D02 (Portfolio Management), Spec D04 (FX Calculation Engine), Spec D09 (Market & FX Data Integration), Spec 00f (Global Configuration)

---

## 1. Purpose

Define how a user records the assets they own within a portfolio, including every individual purchase event (a **lot**) and every sale event, with full preservation of price and exchange-rate context at the moment each event occurred. This is the data foundation on which the FX engine (D04), the indicator catalog (D05), and the price-level/alert system (D06) all depend.

This spec defines the data model and lifecycle. It does **not** define how prices or exchange rates are obtained from external APIs, nor how indicators are computed — those belong to their own specs.

---

## 2. Conceptual model

The data is layered in three levels:

1. **Asset** — the financial instrument itself (e.g. "Apple Inc.", ticker `AAPL`, quoted in USD on Nasdaq). Asset definitions are shared across all users and portfolios; they are reference data, not per-user data.
2. **Holding** — the link between a portfolio and an asset. A holding represents "this portfolio owns this asset." There is exactly one holding per `(portfolio, asset)` pair. The holding aggregates all lots and sales for that asset within that portfolio.
3. **Lot** — a single purchase event. Multiple lots can exist under one holding. Each lot is immutable in concept (a historical fact) but editable while no sale has consumed it (see Section 6).
4. **Sale** — a single sale event. A sale consumes one or more lots in FIFO order (see Section 7).

The UI presents holdings (one entry per asset in the portfolio's main list), with a per-holding detail view that breaks down lots, sales, and aggregated totals. The database stores lots and sales as independent entities.

---

## 3. Entities

### 3.1 `Asset` (shared reference data)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `ticker` | string | E.g. `AAPL`, `BTC-USD`. |
| `name` | string | E.g. "Apple Inc.". |
| `asset_type` | enum | `stock` \| `etf` \| `fund` \| `crypto`. |
| `quote_currency` | string (ISO 4217 or crypto code) | The currency the asset is quoted in. |
| `market` | string, nullable | E.g. "NASDAQ", "BME", or null for crypto. |
| `created_at` | timestamp (UTC) | |

Asset records are created on-demand the first time any user adds that asset to any portfolio, and are then reused by all subsequent users referring to the same ticker. The mechanism for resolving ticker → Asset is defined in Spec D09 §8.

### 3.2 `Holding`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `portfolio_id` | UUID | Foreign key to `Portfolio`. |
| `asset_id` | UUID | Foreign key to `Asset`. |
| `created_at` | timestamp (UTC) | Set when the first lot for this `(portfolio, asset)` pair is created. |
| `updated_at` | timestamp (UTC) | |

Uniqueness constraint: at most one `Holding` per `(portfolio_id, asset_id)` pair. A holding is created automatically when the user adds the first lot of an asset to a portfolio. It is **not** removed automatically when its last lot is deleted (see Section 6.3) — it is only removed via the explicit "delete asset" action (`DELETE /portfolios/{pid}/holdings/{hid}`), which the user triggers deliberately from the asset detail screen.

### 3.3 `Lot` (purchase event)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `holding_id` | UUID | Foreign key to `Holding`. |
| `purchase_date` | date | Date of the purchase. |
| `quantity` | NUMERIC | Number of units purchased. Must be > 0. |
| `unit_price` | NUMERIC | Price per unit, in the asset's `quote_currency`. |
| `fx_rate_at_purchase` | NUMERIC | Exchange rate (1 unit of `quote_currency` → portfolio's `base_currency`) on `purchase_date`. |
| `fx_rate_origin` | enum | `auto` \| `manual` \| `corrected` \| `manual_pending` — tracks how the rate was set. The `manual_pending` value is used when the lot was created but the FX provider was unavailable and the user must enter the rate manually before any calculation can run (see Spec D09 §7.1). |
| `notes` | text, nullable | Free-form user notes for this lot. |
| `quantity_consumed` | NUMERIC | Sum of quantities consumed by all sales referencing this lot. Initially 0. Always ≤ `quantity`. |
| `created_at` | timestamp (UTC) | |
| `updated_at` | timestamp (UTC) | |

`quantity_consumed` is a derived/maintained field updated transactionally whenever a sale is created or deleted. It is what enables the "editable only if not consumed" rule (Section 6.2) and the FIFO consumption logic (Section 7.2).

### 3.4 `Sale` (sale event)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `holding_id` | UUID | Foreign key to `Holding`. |
| `sale_date` | date | Date of the sale. |
| `quantity` | NUMERIC | Number of units sold. Must be > 0. |
| `unit_price` | NUMERIC | Price per unit at sale, in the asset's `quote_currency`. |
| `fx_rate_at_sale` | NUMERIC | Exchange rate (`quote_currency` → portfolio's `base_currency`) on `sale_date`. |
| `fx_rate_origin` | enum | `auto` \| `manual` \| `corrected` \| `manual_pending`. Same semantics as the lot's `fx_rate_origin` (Section 3.3). |
| `notes` | text, nullable | Free-form user notes. |
| `created_at` | timestamp (UTC) | |
| `updated_at` | timestamp (UTC) | |

### 3.5 `SaleLotConsumption` (junction: which lots a sale consumed)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `sale_id` | UUID | Foreign key to `Sale`. |
| `lot_id` | UUID | Foreign key to `Lot`. |
| `quantity_consumed` | NUMERIC | How many units of this lot the sale consumed. > 0. |

This junction table records the FIFO mapping at the time of the sale and is the source of truth for which lots are "touched" by which sales. It enables tracing each sale back to its constituent purchases for tax/realized-gain calculations (future spec).

---

## 4. Asset addition flow

To add an asset to a portfolio (UI Screen 5, "Añadir activo"):

1. User searches for an asset (typeahead by ticker or name).
2. User selects the asset type (stock / ETF / fund / crypto).
3. User enters the first lot's details: `quantity`, `unit_price`, `purchase_date`.
4. The system **automatically** retrieves the exchange rate (`quote_currency` → portfolio's `base_currency`) for `purchase_date`, sets `fx_rate_origin = auto`. The user can override the value before saving, which sets `fx_rate_origin = manual`. If the user edits an auto-populated rate **after** saving, `fx_rate_origin = corrected`.
5. On confirm, the system creates the `Asset` (if it does not already exist), creates the `Holding` (if it does not already exist for this portfolio + asset pair), and creates the first `Lot` for that holding.

Subsequent lots on the same asset within the same portfolio are added via the holding's detail view ("add another lot"), and reuse the existing `Holding` record.

---

## 5. Price and exchange rate sources

For each lot and sale, both the `unit_price` and the FX rate are recorded explicitly. The standard sourcing rules are:

- **At creation time (purchase or sale):** the FX rate for `purchase_date` / `sale_date` is fetched automatically from the configured FX data provider; `fx_rate_origin = auto`.
- **Manual override at creation:** the user can replace the auto value before saving; `fx_rate_origin = manual`.
- **Correction after creation:** if the user edits the FX rate later, `fx_rate_origin = corrected`.
- The `unit_price` is always user-provided; the system does not auto-fetch historical asset prices for past purchase dates.

The **current price** of any holding (used for current valuation and indicator calculations) is fetched separately by the market data layer and is not stored on `Lot` or `Holding` records — it is a live value, not a recorded event.

---

## 6. Editing and deleting lots

### 6.1 Editable fields

All fields of a lot (`purchase_date`, `quantity`, `unit_price`, `fx_rate_at_purchase`, `notes`) are editable, subject to the consumption rule in Section 6.2.

### 6.2 Consumption rule (lots with associated sales)

If a lot has been wholly or partially consumed by one or more sales — i.e. there exists at least one `SaleLotConsumption` record pointing to this lot, equivalently `quantity_consumed > 0` — then:

- **Editing the lot is blocked.** The user receives a clear error explaining that the lot is referenced by one or more sales and cannot be modified until those sales are deleted.
- **Deleting the lot is blocked**, by the same rule.

The user's recourse is to delete the dependent sale(s) first (which restores the consumed quantity to its source lots), after which the lot becomes editable/deletable again.

### 6.3 Deletion behavior

Lot deletion is **permanent (hard delete)** — there is no archive state for lots. The user is asked to confirm before deletion. The parent `Holding` is always preserved, even if this was its last remaining lot and no sales exist — the holding is then shown with zero lots and zeroed aggregates (Section 8). The user can add a new lot to it at any time, exactly as they would for any other holding.

The holding is only removed by the explicit "delete asset" action (Section 3.2), never as a side effect of deleting its last lot.

---

## 7. Sales

### 7.1 Sale creation flow

To register a sale:

1. User selects a holding within a portfolio.
2. User enters `sale_date`, `quantity` (must be ≤ the available units across not-yet-fully-consumed lots), `unit_price`.
3. The FX rate for `sale_date` is sourced per Section 5 (auto / manual / corrected).
4. On confirm:
   - The system consumes lots in **FIFO order** (Section 7.2).
   - A `Sale` record is created.
   - One or more `SaleLotConsumption` records are created, one per lot touched.
   - The `quantity_consumed` field of each touched lot is updated within the same transaction.

The entire operation is atomic.

### 7.2 FIFO consumption algorithm

1. List all lots of the holding where `quantity_consumed < quantity` (i.e. lots with remaining unconsumed units), ordered by `purchase_date` ascending, then by `created_at` ascending as a tie-breaker.
2. Walk the list, consuming from each lot up to `quantity - quantity_consumed` units, until the sale's `quantity` has been fully satisfied.
3. For each lot touched, create a `SaleLotConsumption` row with the exact `quantity_consumed` from that lot, and update the lot's `quantity_consumed` field.
4. If the sale's `quantity` exceeds the total available across all lots, the sale is rejected before any modification — the user is told the requested quantity exceeds their available position.

FIFO is the default and only method in v1. It is the method required by Spanish tax law for retail investors, which is a likely-relevant context for the project owner. A future revision may introduce LIFO or per-portfolio configurable methods, but that is out of scope for v1.

### 7.3 Editing and deleting sales

A sale is editable: `sale_date`, `quantity`, `unit_price`, `fx_rate_at_sale`, and `notes` can all be changed.

However, **editing the `quantity` of a sale triggers a recomputation of its lot consumption**: the system removes the existing `SaleLotConsumption` rows for that sale, restores the `quantity_consumed` of the affected lots, and re-applies the FIFO algorithm with the new quantity. This is atomic.

Deleting a sale removes its `SaleLotConsumption` rows and restores the affected lots' `quantity_consumed` values in the same transaction. The sale is then hard-deleted (no archive).

---

## 8. Aggregated holding views (UI guidance)

The UI presents holdings as a single row per asset within the portfolio, with these computed aggregates available:

- **Total quantity held** = Σ `(lot.quantity - lot.quantity_consumed)` across all lots of the holding.
- **Weighted average purchase price (in quote currency)** = Σ `(unconsumed_quantity × unit_price)` / total quantity held.
- **Weighted average purchase price (in base currency)** = Σ `(unconsumed_quantity × unit_price × fx_rate_at_purchase)` / total quantity held.
- **Total invested (base currency)** = Σ `(unconsumed_quantity × unit_price × fx_rate_at_purchase)` across all lots.

These aggregates are derived, not stored. The detail view of a holding (Asset Detail screen) shows the breakdown lot-by-lot and sale-by-sale, per the design already approved in the functional spec.

The mathematics of the FX-adjusted return per lot, and the decomposition into "asset return vs FX effect," are defined in Spec D04 (FX Calculation Engine).

---

## 9. Cascading deletion (cross-spec consistency)

When a portfolio is permanently deleted per Spec D02, Section 8, all holdings, lots, sales, and `SaleLotConsumption` records belonging to that portfolio are deleted as part of the same atomic operation. This is the concrete realization of the "cascading delete" mentioned in D02.

When a portfolio is archived per Spec D02, Section 6, holdings, lots, and sales are preserved in the database but excluded from any calculation while their parent portfolio's status is `archived`.

---

## 10. Authorization

A user may only see and modify holdings, lots, sales, and consumption records whose parent portfolio belongs to them, per Spec 00b, Section 5.

---

## 11. Out of scope for v1

- **LIFO or other consumption methods** beyond FIFO.
- **Dividends, splits, mergers, and other corporate actions** that adjust quantities or cost basis automatically. In v1, the user records these manually (e.g. as additional lots or notes) if they want to track them.
- **Short positions** (negative quantities).
- **Transfers between portfolios** (e.g. moving a lot from "Personal" to "USA portfolio" with cost-basis preservation).
- **Realized gain/loss reporting and tax summaries** — these will use the data structures defined here but require a separate spec to define the calculation and presentation.
- **Bulk import** from broker CSV files. Manual entry only in v1.
- **Currency conversion between two non-base currencies** within the same portfolio (the portfolio always has exactly one base currency; lots in any quote currency are converted directly to that base).

---

## 12. Rationale

Modeling each purchase and each sale as a first-class event — rather than collapsing them into a single "average cost" per holding — has three benefits that align with the project's stated goals: (a) it preserves the user's historical analysis intact ("I bought at this price, I noted these reasons"), which is the core motivation for the system; (b) it allows the FX engine in D04 to compute the currency effect per lot, which is impossible from an averaged figure; and (c) it makes future features like tax reporting tractable without a data migration, because the granular history is already there.

FIFO is the only consumption method in v1 because making consumption configurable adds branching to almost every downstream calculation (current quantities, realized gains, cost basis) and the project owner has no current need for alternatives. The escape hatch (configurable method later) is preserved by keeping the FIFO logic isolated in the sale-creation flow rather than scattered across the codebase — see implementation guidance in the technical spec derivation.

Blocking edits/deletions of consumed lots (rather than cascading edits down to sales) is a deliberate choice: silent recomputation of sales is risky because it can change a user's reported gains without their understanding, while making the user delete the sale first forces a conscious acknowledgement that they are editing financial history.
