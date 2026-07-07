# Changeset C08 — Portfolio Header (Total Return + 30-Day Trend Chart)

**Status:** Pending implementation
**Type:** Cross-spec changeset
**Triggered by:** New portfolio-level summary block ("portfolioHeader") introduced in the visual redesign, needed on top of the current portfolio detail screen.
**Affects implementations of:** Spec D05 (indicator KPIs), Spec D09 (market data — reads only), Spec D10 (frontend), Spec D08 (i18n), Spec 00f (configuration keys).

---

## 0. How to read this document

This is a **cross-spec changeset**, not a new spec. The portfolio-level KPIs it introduces already have conceptual coverage in D05 §4.6 (portfolio KPIs), which was defined but never wired to real data. C08 wires the minimum viable subset of that so the redesigned portfolioHeader can render.

C08 deliberately restricts scope to **Total Return** and the **30-day trend chart**. The other four KPIs originally listed (CAGR, Max Drawdown, Volatility, Sharpe ratio) are **not implemented in this iteration** and will require a follow-up spec + changeset. See §11.

---

## 1. Motivation

The redesigned portfolio detail screen (Screen 4 per D10) has a new visual block at the top — the **portfolioHeader** — displaying five tiles:

- **VALOR TOTAL** with delta (absolute and %).
- **INVERTIDO** — total capital invested.
- **P&L LAT.** — latent (unrealized) profit and loss.
- **P&L REAL.** — realized profit and loss.
- **30D** — a small line chart showing the trend of the portfolio's total value over the last 30 days.

Two of these tiles cannot be implemented without significant additional work:

- **P&L REAL.** requires realized-gain accounting, which is **explicitly out of scope for v1** per Spec D04 §1 and D04 §10.
- The full set of "portfolio performance indicators" (CAGR, Max Drawdown, Volatility, Sharpe ratio) that the redesign anticipates all require a persisted history of the portfolio's daily value that we do not have yet.

The project owner decided the **minimum viable** first iteration for the portfolioHeader:

- Ship **VALOR TOTAL, INVERTIDO, P&L LAT.** as computed from data already available.
- Ship the **30D chart** computed on-the-fly (no persisted history yet).
- **Hide** the P&L REAL. tile until realized-gain accounting is scoped.
- Defer CAGR / Max Drawdown / Volatility / Sharpe to a future changeset (§11).

---

## 2. Scope decisions locked with the project owner

- **On-the-fly calculation** of the 30-day series, **not** a persisted `PortfolioValueHistory` entity. Rationale: simpler, no schema changes, no daily-job additions. The full-history KPIs (CAGR, MDD, etc.) will require persistence, but they are out of scope here.
- **In-memory server-side cache** for the 30-day series with a 5-minute TTL per portfolio. Mitigates the cost of re-computing on every page load without introducing new infrastructure.
- **`risk_free_rate` configuration key** is added now (not used yet), so the future Sharpe iteration finds it in place. Default: `0.03` (3%, reasonable for EUR base currencies as of 2026).
- The **P&L REAL. tile is not rendered** in v1. When the redesign requires four tiles visually, the layout falls back to three tiles + the chart. This is a deliberate design constraint documented in §7.

---

## 3. Backend — `PortfolioSummary` service (new)

### What changes

A new service class `PortfolioSummaryService` centralizes the computation of the portfolioHeader values. It exposes one entry point:

```python
get_summary(portfolio_id: UUID, user_id: UUID) -> PortfolioSummary
```

Returns a structured object with:

- `total_value` (Decimal, in portfolio base currency).
- `total_invested` (Decimal).
- `unrealized_pnl` (Decimal) — `total_value - total_invested`.
- `unrealized_pnl_pct` (Decimal, e.g. `0.462` for +46.2%).
- `trend_30d` (list of 30 daily points, each with `date` and `value`).
- `computed_at` (timestamp; used by the caching layer).

The service internally uses the existing FX engine (D04) and the existing `AssetPriceHistory` (D09). No new tables. No new provider calls.

### Where in code

- **`backend/app/portfolios/summary_service.py`** — the new service.
- **`backend/app/portfolios/schemas.py`** — extend with the `PortfolioSummary` Pydantic model.
- **Unit tests** in `backend/tests/portfolios/test_summary_service.py`:
  - Portfolio with one active lot: verify values.
  - Portfolio with a lot partially consumed by a sale: `total_invested` reflects only the remaining quantity's cost.
  - Portfolio with holdings in mixed currencies: FX conversion applied consistently per D04.
  - Portfolio without any holdings: all values `0` (no error).
  - `trend_30d` with a portfolio created fewer than 30 days ago: the series starts on the earliest available date (fewer than 30 points is valid).

### Why

Per D05 §4.6 and the redesign, the portfolioHeader needs a single source of truth for portfolio-level KPIs. Encapsulating in one service isolates the on-the-fly calculation and gives the future CAGR/MDD/Volatility/Sharpe work a natural place to plug into.

### Acceptance criteria

- Values match manual calculation on a small test portfolio.
- FX is applied consistently: an asset quoted in USD in a EUR portfolio contributes the correct EUR value both to `total_value` and to `total_invested`.
- Portfolios with 0 holdings return `total_value = 0`, `unrealized_pnl = 0`, `unrealized_pnl_pct = 0`, `trend_30d = []` without error.

---

## 4. Backend — 30-day trend computation (on-the-fly)

### What changes

Inside `PortfolioSummaryService`, implement `_compute_trend_30d(portfolio_id, user_id) -> list[TrendPoint]`:

For each of the last 30 UTC dates (from `today - 29` to `today`):

1. Compute the set of "active lots" at that date (created on or before that date, not fully consumed by sales made on or before that date).
2. For each active holding, retrieve the closing price from `AssetPriceHistory` for that date.
3. Convert to the portfolio's base currency using `FxRateHistory` for that same date (per D04).
4. Sum contributions across holdings.

If a required data point is missing (no price for a date, no FX rate for a date), the day's contribution from that holding is computed with the **last known previous close before that date**, and the entire day's point is marked `estimated = true`. Per Spec D09 §4.3 the system does not silently fall back to stale data for user-visible values without marking it, so this flag propagates to the frontend which renders the estimated segment of the chart with a dashed line.

If **no** data at all is available for a specific date (no price series for any holding at that point), the entire day is omitted from the returned list. This is preferred over inventing `0` values which would produce a misleading dip in the chart.

### Where in code

- Same service file, private method.
- New Pydantic sub-model `TrendPoint`: `{ date: date, value: Decimal, estimated: bool }`.

### Why

Per Spec D09 §5.3, historical prices are immutable and persisted, so on-the-fly retrieval is deterministic — the same call on the same day returns the same series. The 30-day window keeps the on-the-fly cost manageable.

### Acceptance criteria

- A portfolio with 5 holdings requires ≤ 150 `AssetPriceHistory` lookups + ≤ 150 `FxRateHistory` lookups per computation (30 days × 5 holdings, minus same-currency holdings).
- Missing intermediate data → the day is marked `estimated`, not silently faked.
- Missing all data for a day → the day is omitted from the response.
- Verified performance: on a test portfolio of 10 holdings, computation completes in < 200 ms on a laptop-class machine.

---

## 5. Backend — In-memory cache with 5-minute TTL

### What changes

Wrap `PortfolioSummaryService.get_summary(portfolio_id, user_id)` with a simple in-memory cache. Key: `(portfolio_id, user_id, current_date_utc)`. TTL: 5 minutes. On cache hit, return the cached `PortfolioSummary` directly.

The cache is process-local (no Redis, no shared cache). Multiple backend workers each have their own cache; this is acceptable for the personal-use MVP.

The cache is invalidated:
- On expiry (5 minutes).
- On rollover to a new UTC date (the cache key includes `current_date_utc`).
- **Explicitly** when any of the following operations succeeds:
  - A lot is created, edited, or deleted (Spec D03).
  - A sale is recorded (Spec D03).
  - A holding is added or removed (Spec D03).

The service exposes `invalidate(portfolio_id)` for these operations to call. The invalidation removes all entries for `portfolio_id` regardless of `user_id`.

### Where in code

- **`backend/app/portfolios/summary_cache.py`** — new module with a `TTLCache`-like structure. Use `cachetools` if it is already in the project; otherwise implement in ~30 lines with a dict + a small `time.monotonic()` check. **Do not add `cachetools` as a new dependency** without confirming.
- **Integration points**: `backend/app/lots/service.py`, `backend/app/sales/service.py`, `backend/app/holdings/service.py` — each write path calls `summary_cache.invalidate(portfolio_id)` after commit.

### Why

Per §2, the caching keeps the on-the-fly cost off the user's critical path when they navigate between the portfolio screen and back. The 5-minute TTL is short enough that prices refreshed by the daily job show up promptly.

### Acceptance criteria

- First call on a cold cache computes the summary and stores it; subsequent calls within 5 minutes return the cached result (verifiable by checking that no DB queries fire on the second call).
- Creating a lot invalidates the cache for that portfolio: the next call re-computes.
- Cache is not shared across processes (accepted trade-off, documented).

---

## 6. Backend — REST endpoint

### What changes

New endpoint:

```
GET /portfolios/{portfolio_id}/summary
```

Returns the `PortfolioSummary` payload. Guarded by `Depends(require_permission("portfolio.view"))` (existing permission per D11 §5.1, applied to `investor` and `administrator` roles by default).

Response shape:

```json
{
  "total_value": "18240.00",
  "total_invested": "12480.00",
  "unrealized_pnl": "5760.00",
  "unrealized_pnl_pct": "0.462",
  "trend_30d": [
    { "date": "2026-11-15", "value": "17800.00", "estimated": false },
    { "date": "2026-11-16", "value": "17920.00", "estimated": false },
    { "date": "2026-11-17", "value": "18100.00", "estimated": true }
  ],
  "computed_at": "2026-12-14T18:22:41Z",
  "base_currency": "EUR"
}
```

Decimal values are sent as **strings** to preserve precision (consistent with Spec D10 §7.4).

### Where in code

- **`backend/app/api/portfolios.py`** — add the endpoint. Delegate to `PortfolioSummaryService` (which delegates to the cache which delegates to the computation).

### Acceptance criteria

- A user requesting the summary of a portfolio they do not own → HTTP 404 (never 403 — do not leak the existence of other users' portfolios; consistent with Spec 00b §5).
- A user requesting a valid portfolio → 200 OK with the payload.
- An archived portfolio (Spec D02 §6) → the endpoint still returns the summary; archived does not mean unreadable.

---

## 7. Frontend — `pi-portfolio-header` component

### What changes

New Web Component `<pi-portfolio-header>` implementing the redesigned block:

**Layout** — a horizontal band with:
1. **VALOR TOTAL** tile: the value, the absolute delta (green/red arrow), and the percentage delta below.
2. **INVERTIDO** tile: the total invested.
3. **P&L LAT.** tile: `unrealized_pnl`, formatted per Spec D08 §7.
4. **30D chart** tile: a small line chart, ~120px wide × 60px tall.

The **P&L REAL. tile is NOT rendered in v1**. The layout accommodates four elements (three tiles + chart) instead of the five in the mockup. See §11 for the rationale on deferring P&L REAL.

**Data flow:**
- The component receives `portfolioId` as an attribute.
- On mount, it calls `GET /portfolios/{portfolioId}/summary` via `src/api/portfolios.ts`.
- While loading: render skeleton placeholders in each tile.
- On success: render the values with proper formatting.
- On error: render a compact error state ("No se pudo cargar el resumen") with retry button.

**Formatting:**
- Numbers formatted via `Intl.NumberFormat` per Spec D08 §7.2.
- Currency symbol from `base_currency` (Spec D08 §7.3).
- Delta color: green for positive, red for negative, neutral gray for exactly zero.

### Where in code

- **`frontend/src/components/portfolio-header.ts`** — the component.
- **`frontend/src/api/portfolios.ts`** — add `getPortfolioSummary(portfolioId)`.
- **`frontend/src/screens/dashboard-screen.ts`** — mount `<pi-portfolio-header portfolio-id="...">` above the existing content.

### Why

Per the visual redesign, the portfolioHeader is the primary summary the user sees when opening a portfolio. It should feel instant (via caching) and accurate (real values, not placeholders).

### Acceptance criteria

- Loading state renders within 16ms of mount.
- Values match the API response exactly, with proper Spanish (comma decimal) or English (dot decimal) separators depending on `currentLanguage`.
- The 30D chart renders correctly with 30 (or fewer) points.
- Deltas display with correct color and sign.
- The layout adapts responsively: on mobile (< 640px), the tiles stack vertically instead of side-by-side.

---

## 8. Frontend — 30D line chart

### What changes

The 30D chart inside `pi-portfolio-header` is a **minimal SVG line chart** rendered without any charting library:

- One `<polyline>` with the 30 `(date, value)` points normalized to fit the tile.
- Estimated points (per §4) rendered with a dashed stroke instead of solid.
- No axes, no labels, no legend. It is a **sparkline**, not a full chart. This matches the compact design of the mockup.
- Hovering the chart shows a tooltip with the exact value on the hovered day. On mobile, tap-to-show.

**No new charting dependency**. The full Chart.js / d3 approach is deferred to a hypothetical future spec.

### Where in code

- **`frontend/src/components/portfolio-trend-sparkline.ts`** — the SVG-rendering component, called from `pi-portfolio-header`.

### Why

Per §2 and the "no new runtime dependencies" rule of D10 §2, adding a charting library for a single sparkline is disproportionate. ~50 lines of hand-written SVG code is enough.

### Acceptance criteria

- The sparkline renders a smooth line for 30 days of solid data.
- Days with `estimated = true` render as dashed segments seamlessly.
- The tooltip on hover / tap shows the correct value.
- Adapts to the container width without distortion (`preserveAspectRatio`).

---

## 9. Configuration keys (added to Spec 00f)

Two new keys added to `config.yaml` and to Spec 00f's registry:

| Key | Type | Default | Description |
|---|---|---|---|
| `portfolio.summary.cache_ttl_seconds` | integer ≥ 0 | `300` | TTL of the in-memory portfolio summary cache. Set to `0` to disable caching (useful for debugging). |
| `portfolio.performance.risk_free_rate` | Decimal (0.0–0.20) | `0.03` | Annual risk-free rate used by future Sharpe ratio calculation. Not consumed by v1; added preemptively so a future changeset finds it in place. |

The registry table in Spec 00f is updated in lockstep (same narrow exception used for prior changesets).

---

## 10. Translations (Spec D08)

Add the following keys to `frontend/src/i18n/locales/es.json` and `en.json`:

| Key | Spanish | English |
|---|---|---|
| `portfolio_header.total_value` | Valor total | Total value |
| `portfolio_header.invested` | Invertido | Invested |
| `portfolio_header.unrealized_pnl` | P&L latente | Unrealized P&L |
| `portfolio_header.trend_30d` | 30 días | 30 days |
| `portfolio_header.loading_error` | No se pudo cargar el resumen | Could not load summary |
| `portfolio_header.retry` | Reintentar | Retry |
| `portfolio_header.tooltip.estimated` | Valor estimado (datos incompletos) | Estimated value (incomplete data) |

Run the i18n validator introduced in C06 §3 to verify no other keys are missing.

---

## 11. Deferred to future changesets (out of scope for C08)

### 11.1 P&L Realized

Realized gain accounting is out of scope for v1 per Spec D04 §1, §10. Introducing it requires:

- Extending `Sale` (Spec D03 §3.4) with per-lot cost basis logic.
- A `RealizedGain` calculation that iterates over `SaleLotConsumption` rows.
- Integration into the FX engine so cross-currency sales are computed correctly.

A separate spec **D13 — Realized Gain Accounting** should scope this properly. Until then, the portfolioHeader hides the P&L REAL. tile.

### 11.2 CAGR, Max Drawdown, Volatility, Sharpe

These four indicators all require a **persisted daily history of the portfolio value**, since they use time series of arbitrary length (years, not 30 days). Introducing them requires:

- A new entity `PortfolioValueHistory` (`portfolio_id`, `date`, `value`, `source = 'daily_job' | 'backfill'`).
- Extending the daily job (Spec D05 §6.1) to append one row per portfolio per day.
- A one-time backfill routine to populate history for existing portfolios from their `AssetPriceHistory` (bounded by the earliest known price date per holding).
- Calculation modules for each indicator with proper handling of gaps, dividends, and portfolio composition changes (adding/removing holdings mid-period is non-trivial).

A separate spec **D14 — Portfolio Performance Analytics** should scope this. C08's decision to compute the 30-day trend on-the-fly is explicitly a **stopgap** valid only for the 30-day window; it does not scale to full history.

### 11.3 Full charting library

If future charts need axes, multiple series, zooming, or export to image, introducing a charting library (Chart.js is the current candidate) will require its own spec + changeset. The sparkline in C08 is the minimum footprint.

---

## 12. Order of implementation

1. **Step 1 — Backend service without cache** (§3, §4). Verify correctness against test portfolios first.
2. **Step 2 — Backend endpoint** (§6). At this point the frontend can be developed against a working API.
3. **Step 3 — Configuration keys** (§9) — additive, no runtime effect yet.
4. **Step 4 — Cache** (§5). Verify invalidation on lot/sale/holding operations before proceeding.
5. **Step 5 — Frontend translations** (§10) — additive.
6. **Step 6 — Frontend component and sparkline** (§7, §8). Wire to the dashboard screen last.

Each step should be one or more commits with `feat(portfolio-header): …` prefix.

---

## 13. What this changeset does not change

- **Spec D04 (FX engine)** — unchanged, only consumed.
- **Spec D09 (Market & FX data integration)** — unchanged, only consumed for historical values.
- **Spec D05 (Indicator Catalog)** — the portfolio KPI slot §4.6 already existed; C08 is the first real usage but does not modify the spec.
- **Spec D03 (Lots and sales)** — unchanged. C08 reads them.
- **Spec D11 (Roles)** — no new permission needed; `portfolio.view` already covers the new endpoint.

---

## 14. Out of scope (recap)

- P&L Realized (deferred to D13).
- CAGR / MDD / Volatility / Sharpe (deferred to D14).
- Persisted `PortfolioValueHistory` (part of D14).
- Charting library (deferred).
- Backfilling historical portfolio value for old portfolios (part of D14).
- Chart interactions beyond a simple tooltip (deferred).
- Multi-currency display (the header shows values in the portfolio's base currency only; per-holding original currencies remain accessible on the detail rows below).
