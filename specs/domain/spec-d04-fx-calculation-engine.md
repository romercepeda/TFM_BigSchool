# Spec D04 — FX Calculation Engine

**Status:** Approved
**Type:** Domain capability
**References:** Spec D02 (Portfolio Management), Spec D03 (Asset Holdings, Purchase Lots & Sales), Spec 00c (Testing Strategy)

---

## 1. Purpose

Define the deterministic, pure calculation engine that converts purchase lots, current prices, and exchange rates into the three figures shown to the user for every lot and aggregated holding:

1. **Asset return** — the return of the asset itself, in its own quote currency.
2. **Base currency return** — the return as the user actually experiences it, in the portfolio's base currency.
3. **FX effect** — the difference between the two, attributed to currency movement.

This spec covers calculations for **unrealized** positions only (i.e. lots still held, partially or fully). Calculations involving **realized** sales (gain/loss reporting, tax summaries) are out of scope and will be defined in a future spec.

This is the most mathematically critical component of the system. Per Spec 00c, it carries a coverage target of **90-100%** on the unit tests.

---

## 2. Scope of calculations

The engine produces results at two levels:

- **Per-lot**: a single lot of a single holding. Inputs: lot data + current price + current FX rate.
- **Aggregated total per holding**: the holding-level summary across all of its unconsumed lot quantities. The aggregation uses the per-lot results as building blocks.

Out of scope for this spec: holding-level realized gain (requires sales), portfolio-level KPIs (TWR, CAGR, Drawdown, Volatility, Sharpe — these are part of the indicators catalog spec, D05), per-sale calculations.

---

## 3. Conventions

### 3.1 Exchange rate notation

Throughout this spec and the implementation, an FX rate is **always expressed as: how many units of the base currency one unit of the quote currency buys**.

Example: for a portfolio in EUR holding an asset quoted in USD, an FX rate of `0.93` means *1 USD = 0.93 EUR*. To convert a price `P` in USD into EUR, multiply: `P × 0.93`.

This is the "direct quote" from the portfolio's perspective. Every `fx_rate_at_purchase`, `fx_rate_at_sale`, and `fx_rate_current` field in the system follows this convention. Implementations and tests must adhere to it without exception.

### 3.2 Numeric precision

| Quantity type | Internal precision (stored / computed) | Display precision |
|---|---|---|
| Exchange rates | 4 decimal places | 4 decimal places |
| Prices in fiat currencies (EUR, USD, GBP, JPY, CHF, CAD, AUD) | 4 decimal places | 2 decimal places |
| Prices in crypto-quoted assets | 8 decimal places | up to 8 (UI may truncate based on magnitude) |
| Asset quantities (units held) | 8 decimal places | up to 8 (UI shows what is needed) |
| Returns and ratios (as decimal fractions, e.g. `0.0612` for 6.12%) | 4 decimal places | 2 decimal places (i.e. shown as 6.12%) |
| FX effect (in percentage points) | 4 decimal places | 2 decimal places (shown as e.g. `-10.83 pp`) |

All internal arithmetic is performed using a fixed-precision decimal type (in Python: `decimal.Decimal`). Floating-point types (`float`) are **prohibited** for any value that participates in monetary calculations, per Spec 00a, Section 5.

Rounding mode: **ROUND_HALF_EVEN** ("banker's rounding") — the standard for financial calculations because it does not bias accumulated errors in either direction.

### 3.3 Aggregation notation

Throughout the per-holding aggregation formulas (Section 6), summation `Σ` runs over all lots `i` of the holding where `quantity_i - quantity_consumed_i > 0` — i.e. lots with remaining unconsumed units. Fully consumed lots are excluded from the aggregation. The remaining quantity of a lot is denoted `q_remaining_i = quantity_i - quantity_consumed_i`.

---

## 4. Inputs

The engine is a pure function: given the same inputs, it produces the same outputs, with no side effects.

### 4.1 Per-lot inputs

| Input | Source | Notes |
|---|---|---|
| `quantity_remaining` | `lot.quantity - lot.quantity_consumed` | The unconsumed units in this lot. |
| `unit_price_at_purchase` | `lot.unit_price` | In the asset's quote currency. |
| `fx_rate_at_purchase` | `lot.fx_rate_at_purchase` | Per Section 3.1 convention. |
| `current_unit_price` | Live market data | In the asset's quote currency. |
| `fx_rate_current` | Live FX data | Per Section 3.1 convention. |

### 4.2 Per-holding inputs

The set of per-lot inputs above for every lot of the holding with `quantity_remaining > 0`.

---

## 5. Per-lot calculations

For one lot `i`:

### 5.1 Cost basis

- `cost_in_quote_currency_i = q_remaining_i × unit_price_at_purchase_i`
- `cost_in_base_currency_i  = q_remaining_i × unit_price_at_purchase_i × fx_rate_at_purchase_i`

### 5.2 Current value

- `current_value_in_quote_currency_i = q_remaining_i × current_unit_price`
- `current_value_in_base_currency_i  = q_remaining_i × current_unit_price × fx_rate_current`

### 5.3 Returns

- **Asset return** (return of the asset, in its own quote currency):
  ```
  asset_return_i = (current_unit_price − unit_price_at_purchase_i) / unit_price_at_purchase_i
  ```
  Expressed as a decimal fraction (e.g. `0.0612` = 6.12%).

- **Base currency return** (return as the user actually experiences it):
  ```
  base_return_i = (current_value_in_base_currency_i − cost_in_base_currency_i) / cost_in_base_currency_i
  ```

- **FX effect** (the contribution of currency movement to the difference between the two returns):
  ```
  fx_effect_i = base_return_i − asset_return_i
  ```
  Expressed in **percentage points** (pp) when displayed.

### 5.4 Edge cases

- **Zero or negative `unit_price_at_purchase`**: cannot occur because Spec D03 requires `unit_price > 0` on lot creation. If somehow encountered, the engine raises a domain error rather than dividing by zero or returning a misleading value.
- **Zero or negative `q_remaining`**: the lot is fully consumed and excluded from aggregation; the engine returns null/no-op for this lot rather than producing meaningless figures.
- **Quote currency = base currency** (e.g. a EUR-quoted asset in a EUR portfolio): `fx_rate_at_purchase` and `fx_rate_current` are both `1.0000`. The formulas above still apply unchanged and produce `fx_effect_i = 0` exactly. This case is not special-cased in code; it is handled by the same formulas as any other case.

---

## 6. Per-holding aggregation

The aggregated holding-level figures combine all unconsumed lots of the holding.

### 6.1 Aggregated cost and value

- `total_cost_quote = Σ cost_in_quote_currency_i`
- `total_cost_base  = Σ cost_in_base_currency_i`
- `total_value_quote = Σ current_value_in_quote_currency_i`
- `total_value_base  = Σ current_value_in_base_currency_i`

### 6.2 Aggregated returns

- **Aggregated asset return** (weighted by cost in quote currency):
  ```
  asset_return_total = (total_value_quote − total_cost_quote) / total_cost_quote
  ```

- **Aggregated base currency return** (weighted by cost in base currency):
  ```
  base_return_total = (total_value_base − total_cost_base) / total_cost_base
  ```

- **Aggregated FX effect**:
  ```
  fx_effect_total = base_return_total − asset_return_total
  ```

The aggregation is naturally cost-weighted — lots with larger total cost contribute proportionally more to the aggregate return. The aggregated FX effect is **not** the simple average of per-lot FX effects; it emerges from the cost-weighted aggregate returns. This is the correct accounting interpretation and must be implemented as written, not as a per-lot average.

### 6.3 Aggregated edge cases

- **`total_cost_quote = 0` or `total_cost_base = 0`**: no remaining position. Aggregated returns are undefined; the engine returns a "no position" status for the holding rather than dividing by zero.
- **Single-lot holding**: all aggregates equal the per-lot values for that lot.

---

## 7. FX rate availability

The engine assumes the caller provides `fx_rate_at_purchase` (already stored on the lot) and `fx_rate_current` (resolved at calculation time). It does **not** fetch FX data itself; that is the responsibility of the market/FX data integration layer (Spec D09).

### 7.1 Missing or unavailable rates

Two distinct cases must be handled at the boundaries of the engine (i.e. by the layer that calls the engine, not by the engine itself):

1. **Currency pair entirely unsupported** (the FX data provider does not offer the pair under any circumstance). This case must be detected **at the moment the user tries to add an asset whose quote currency is not convertible to the portfolio's base currency**, and the addition must be rejected with a clear error before any lot is created. The engine therefore never receives lots in this state.

2. **Spot rate not available for a specific historical date** (e.g. weekend, holiday, gap in provider data) for an existing lot. The lot exists, but a specific `fx_rate_at_purchase` could not be auto-fetched at creation time. In this case:
   - The lot is still saved, but with a sentinel `fx_rate_at_purchase = NULL` (or equivalent representation, to be finalized in the technical schema).
   - The user is prompted to enter the value manually (`fx_rate_origin = manual`) before any calculation involving that lot can run.
   - If the calculation engine is asked to compute a lot with a null `fx_rate_at_purchase`, it returns a structured **"FX rate missing"** status for that lot, which propagates up: per-lot results carry the status, and holding-level aggregates exclude the affected lots and surface the status to the UI. The UI shows the literal label *"Falta tipo de cambio"* (translated per i18n) on the affected position.

The engine is otherwise stateless and does not retry, log, or notify. Resolution is a UI responsibility.

### 7.2 No triangular conversion

The engine **never** performs triangular conversion (e.g. JPY → USD → GBP) to substitute for an unavailable direct rate. This is a deliberate decision: synthetic cross rates would silently change the user's calculations using arithmetic the user did not choose. The fail-loud behavior in Section 7.1 is preferred.

If the market/FX data layer chooses to source a cross rate from the upstream provider — because the provider itself offers the cross rate as a first-class quotation — that is acceptable and transparent to the engine (the engine only sees a direct rate). What is prohibited is the **system** synthesizing such a rate from two unrelated quotes.

---

## 8. Determinism and purity

The engine is a **pure function** of its inputs. It:
- Has no I/O (no network, no database, no file system, no clock reads).
- Has no hidden state.
- Produces identical outputs for identical inputs across runs.

This is what enables the high test coverage target: every formula in Sections 5 and 6 can be unit-tested directly with hand-computed expected values, independent of any infrastructure.

---

## 9. Test scenarios (mandatory baseline)

Per Spec 00c, Section 4, the following scenarios must be covered by unit tests. This is a baseline, not an exhaustive list.

**Per-lot tests:**

1. Quote currency = base currency, gain (asset return > 0, fx_effect = 0).
2. Quote currency = base currency, loss (asset return < 0, fx_effect = 0).
3. Quote currency ≠ base currency, asset gains, FX favorable to the user (both returns positive, fx_effect > 0).
4. Quote currency ≠ base currency, asset gains, FX unfavorable to the user (asset_return > 0, base_return smaller or negative, fx_effect < 0). **This is the Intel example documented in earlier conversation and must be tested with realistic numbers.**
5. Quote currency ≠ base currency, asset loses value, FX favorable (loss mitigated or reversed in base currency).
6. Quote currency ≠ base currency, asset loses value, FX unfavorable (loss amplified in base currency).
7. Asset return = 0 exactly, FX moved (fx_effect = base_return).
8. Lot with `q_remaining = 0` returns no-position status.
9. Lot with `fx_rate_at_purchase = NULL` returns "FX rate missing" status.

**Per-holding tests:**

10. Single lot → aggregate equals per-lot values.
11. Two lots in same quote currency, different purchase dates and FX rates → cost-weighted aggregation produces a return that lies between the per-lot returns.
12. Two lots, one fully consumed, one partially remaining → only the remaining quantity participates.
13. Two lots, one with FX rate missing, one without → aggregate computes from the available lot and propagates the missing-rate status.

The numeric expected values in each test are pre-computed manually (or with a spreadsheet) and stored as fixtures.

---

## 10. Out of scope for v1

- Realized gain/loss calculations from sales (this depends on per-sale FX data already captured in D03, but the calculation logic is a separate spec).
- Cumulative cost-basis methods other than what naturally falls out of the formulas above (no LIFO-equivalent reporting, no tax-lot accounting variants).
- Currency hedging adjustments.
- Real-time streaming of recalculations (recalculation is on-demand per Section 11).
- Inflation-adjusted (real) returns.

---

## 11. Performance and freshness

- All calculations are performed **on demand**, at the time the UI requests them (e.g. on Dashboard load, on Asset Detail open).
- The "current FX rate" is requested fresh from the FX data layer on every recalculation. No internal caching of FX rates is performed by the engine itself; caching policy, if any, belongs to the market/FX data layer and does not change the engine's contract.
- The engine is fast enough that recomputing all lots of a typical personal portfolio (estimated ≤ 100 lots) per request is acceptable without optimization in v1.

---

## 12. Rationale

The engine is deliberately specified as a pure function, with all external dependencies (price data, FX data, persistence) handled by the layers above it. This separation is what makes the 90-100% unit test coverage achievable and meaningful: the formulas can be tested in isolation, with hand-computed expected values, in milliseconds, with no infrastructure dependency. This is the standard approach for any system where the correctness of financial figures is the primary concern, and it directly supports the project's testing strategy.

The decision to define the FX effect as `base_return − asset_return` (rather than computing it from FX rate movements directly) keeps the relationship between the three reported numbers exact by construction: `base_return = asset_return + fx_effect`, identically. The user can rely on this identity to reason about their results.

The refusal to perform synthetic triangular conversion follows the project's broader pattern of preferring **explicit failure** over **silent approximation** when a calculation would otherwise produce a number the user did not implicitly authorize.
