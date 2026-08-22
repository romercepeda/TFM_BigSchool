# Spec D09 — Market & FX Data Integration

**Status:** Approved
**Type:** Domain capability
**References:** Spec D03 (Asset Holdings, Purchase Lots & Sales), Spec D04 (FX Calculation Engine), Spec D05 (Indicator Catalog & Historical Snapshots), Spec D06 (Price Levels, Alerts & Analysis History), Spec 00b (Security Practices), Spec 00f (Global Configuration)

---

## 1. Purpose

Define how the system obtains, persists, and serves the two categories of external data on which most of its business logic depends:

1. **Market data** — current and historical prices for stocks, ETFs, funds, and crypto assets. Consumed by Spec D04 (FX engine, current value calculation), Spec D05 (indicator computation), and Spec D06 (alert detection).
2. **FX (foreign exchange) data** — current and historical exchange rates between the asset's quote currency and the portfolio's base currency. Consumed by Spec D03 (lot creation), Spec D04 (return computation), and Spec D05 (portfolio KPIs in base currency).

This spec is the connection point between the project's business logic and the outside world. Every other domain spec assumes that these data are available; this spec is what makes that assumption true.

---

## 2. Conceptual model

Three layers, with clear separation of responsibilities:

1. **Provider adapters** — concrete implementations that talk to one specific external API (Twelve Data, Finnhub, Frankfurter). Each adapter knows how to format requests, parse responses, and surface errors for one provider.
2. **Data service layer** — a provider-agnostic interface that the rest of the application calls. Resolves the active provider at runtime and delegates. This is what D04, D05, and D06 actually depend on; they never import or reference any provider directly.
3. **Persistence layer** — local PostgreSQL tables that cache historical price series and FX rates. After the first successful fetch of any historical data point, it is stored locally and the provider is never consulted for that same data point again.

The adapter pattern mirrors the one chosen in Spec D07 for LLM providers, and for the same reasons: provider-independence at the business-logic level, configurable provider selection, and portability across hosting environments.

---

## 3. Provider selection

Two distinct provider concerns: market data and FX data. Each is configured independently.

### 3.1 Market data provider

Two adapters are implemented in v1: `TwelveDataProvider` and `FinnhubProvider`. The active one is chosen via configuration key `market_data.provider` (Section 12).

| Provider | Free tier (as of project start) | Notes |
|---|---|---|
| Twelve Data | 800 API calls/day, 4-hour delay on prices | Default. Closest spiritual replacement to the deprecated Yahoo Finance API, broad coverage including international markets. |
| Finnhub | 60 API calls/minute on free tier, includes fundamentals/news | Alternative. Tighter daily implicit cap if used continuously but higher burst rate. |

Both rate-limit figures are operational realities at project inception, not contractual guarantees. The numbers may change over time; the application reads them from configuration (Section 12) rather than from constants, so they can be adjusted without code changes.

### 3.2 FX data provider

One adapter in v1: `FrankfurterProvider`. The architecture supports adding more (the same adapter interface applies), but Frankfurter is sufficient for v1 because:

- It is fully free, requires no API key, has no rate limit.
- It uses European Central Bank reference rates, well-suited for retail-investor calculations.
- It covers all seven base currencies defined in Spec D02 (EUR, USD, GBP, JPY, CHF, CAD, AUD).
- It provides historical data from 1999 onward, more than enough for any plausible purchase history.

The active FX provider is selected via configuration key `fx_data.provider`, with the only allowed value in v1 being `frankfurter`. The configuration key exists from day one for forward compatibility.

---

## 4. The adapter interface

A single Python interface (`MarketDataProvider`) covers market data; a parallel one (`FxDataProvider`) covers FX data. Each interface has a small, focused set of methods.

### 4.1 `MarketDataProvider` interface

```python
search_assets(query: str) -> list[AssetSearchResult]
get_current_price(ticker: str) -> PricePoint
get_historical_series(ticker: str, start_date: date, end_date: date) -> list[PricePoint]
```

- `search_assets` powers the typeahead on the "Add asset" screen (Spec D03 §4 step 1).
- `get_current_price` returns a single price point (price + timestamp + currency code).
- `get_historical_series` returns daily closes for the requested range, sorted ascending by date.

Each provider's adapter normalizes the provider-specific response into the common shape. Errors from the upstream API (rate-limit `429`, timeouts, malformed responses, unknown ticker) are surfaced as a common typed error so the calling code is provider-agnostic.

### 4.2 `FxDataProvider` interface

```python
get_current_rate(quote_currency: str, base_currency: str) -> FxPoint
get_historical_rate(quote_currency: str, base_currency: str, on_date: date) -> FxPoint
is_pair_supported(quote_currency: str, base_currency: str) -> bool
```

Rates are always expressed in the direct-quote convention defined in Spec D04 §3.1: how many units of `base_currency` one unit of `quote_currency` buys.

`is_pair_supported` is used at the moment of asset addition (Spec D04 §7.1 case 1) — to reject in advance any asset whose quote currency is not convertible to the portfolio's base currency.

### 4.3 Provider failure mode

When any provider call fails for any reason (network, rate limit exceeded, unknown ticker, malformed response):

- The adapter raises a typed `ProviderError` with structured detail (`error_kind`, `retryable: bool`, `upstream_message`).
- The data service layer **does not** automatically retry within a single request — retries are time-window-based and live in the daily-job flow (Section 6), not in user-facing calls.
- The data service layer **does not** fall back to stale cached data. Per the project owner's decision (§9), the system surfaces the error to the user with a clear "datos no disponibles" message rather than presenting potentially misleading old values without distinction.

---

## 5. Persistence of historical data

The first time the system fetches any historical price point or historical FX rate, the result is persisted in the database. Subsequent needs for the same data point read from the database, not from the provider.

### 5.1 `AssetPriceHistory` entity

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `asset_id` | UUID | Foreign key to `Asset` (Spec D03 §3.1). |
| `as_of_date` | date | The trading date the price represents. |
| `close_price` | NUMERIC | Closing price for that date, in the asset's quote currency. Precision per Spec D04 §3.2. |
| `provider` | enum (`twelve_data` \| `finnhub`) | Which provider supplied the data. Useful for audit and for catching cases where two providers disagree about a date. |
| `fetched_at` | timestamp (UTC) | When the data was retrieved and persisted. |

Uniqueness constraint: `(asset_id, as_of_date)`. Per-date data is stored once and never duplicated. If a second fetch attempt is made for the same `(asset_id, as_of_date)`, the existing row is **not** updated — the original value is preserved. This is a deliberate choice (Section 5.3).

### 5.2 `FxRateHistory` entity

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `quote_currency` | string (ISO 4217) | |
| `base_currency` | string (ISO 4217) | |
| `as_of_date` | date | |
| `rate` | NUMERIC | Per Spec D04 §3.1 convention: how many `base_currency` one `quote_currency` buys. Precision: 4 decimals per Spec D04 §3.2. |
| `provider` | string | Always `frankfurter` in v1. |
| `fetched_at` | timestamp (UTC) | |

Uniqueness constraint: `(quote_currency, base_currency, as_of_date)`. Same immutability rule as `AssetPriceHistory`.

### 5.3 Immutability of stored historical data

Historical prices and FX rates, once stored, are never overwritten *across trading days*. A second fetch returning a different value for a past date does not update the stored row. This is intentional, for two reasons:

- Financial calculations should not change retroactively. A user who saw a 12% gain yesterday should not see 11.7% today because a data provider issued a correction.
- Providers occasionally publish small revisions (cents-level) that would silently shift downstream KPIs without any user-visible explanation.

When a re-fetch produces a different value for a past date, a warning is logged with both values for diagnosis, but the database row is left as-is. The exception is **manual correction**: an administrator may correct a stored value directly via a database operation if a fetch obviously captured corrupt data. This is not exposed as an application endpoint in v1.

The one other exception is **today's own row** (Changeset C21) — see §5.4.

### 5.4 Current prices: cache-only, with a persisted manual refresh

Current (intraday or most-recent) prices are **not** persisted in their own dedicated table. They are fetched fresh by the daily job (Section 6) and stored as the latest entry of `AssetPriceHistory` for the trading day they cover.

Outside the daily job, current prices are fetched live in exactly one place: an explicit, user-triggered refresh action on the asset detail screen (Changeset C19 — the refresh icon on the "Current Price" card, `POST /market-data/assets/{ticker}/price/refresh`). Changeset C19 originally made this result transient (shown to the user but never written back). Changeset C21 corrected that: the refresh endpoint now upserts the fetched price into *today's* `AssetPriceHistory` row (`MarketDataService.refresh_and_store_current_price`), so it becomes the stored "current price" and survives leaving and re-entering the screen — a manual refresh is a newer, explicit observation than whatever the daily job or an earlier refresh wrote for today, so overwriting today's row (never a past day's, per §5.3) is correct. Every other read of "current price" (the asset detail screen's automatic load, the define-levels form's price pre-fill) is cache-only — it reads the last value the daily job (or a prior manual refresh) produced, and does not call the live provider.

---

## 6. The daily price-update job

Per Spec D05 §6.1, a single daily background job updates technical indicators for every asset held in any non-archived holding. This spec defines what that job does at the data layer.

### 6.1 Job execution

- **Trigger:** Celery beat schedule, time configured via `indicators.scheduled_job.daily_run_hour_utc` (Spec 00f §7.4, default 02:00 UTC).
- **Scope:** every distinct `Asset` referenced by at least one active holding across all users. The job iterates one asset at a time.
- **Per-asset action:** the job calls `get_historical_series(ticker, start_date=earliest_needed, end_date=today)` against the active market data provider. `earliest_needed` is computed as today minus the longest lookback window required by any indicator (200 days for MA200), so a single call retrieves all data needed for every indicator that day.
- **Result handling:** the returned price series is upserted into `AssetPriceHistory`. Per Section 5.3, only new dates produce new rows; existing dates are left untouched.
- **Indicator computation:** once new price points are stored, the indicator calculators (per Spec D05 §8) are invoked for that asset.
- **Alert evaluation:** finally, the alert engine (per Spec D06 §5.5) re-evaluates all armed price levels for every holding that contains this asset.

### 6.2 Rate limit budget

The free tier of Twelve Data allows 800 API calls/day. Per the project owner's decision (§7), each asset triggers a full historical-series call once per day, regardless of whether the asset's data is already mostly cached. This is a deliberate simplicity-over-efficiency trade-off, accepted with the following operational implication:

> With 2 calls per asset per day (1 for price series, 1 for any provider-side market info refresh), the system supports up to **~400 assets in scheduled rotation** before saturating the Twelve Data free tier. Beyond that, the project owner must either upgrade the provider plan, switch to Finnhub via the configuration, or move to a more efficient incremental fetch strategy.

This is a known limit, documented here rather than hidden. It is not relevant at MVP scale (personal portfolio of dozens of assets at most) but should not be forgotten if the system ever expands.

### 6.3 Failure isolation and retry policy

Per Spec D05 §6.1 and §6.2: a failure to fetch data for one asset must not stop the rest of the job. Errors are logged with sufficient context. The asset that failed is **not retried within the same job execution** — the next day's run will try again. There is no separate retry-only job in v1.

If a `ProviderError` of kind `rate_limited` is encountered mid-job (e.g. the daily quota was exhausted before completing all assets), the job **stops cleanly** rather than continuing to send doomed requests. The remaining assets are logged as "not updated today, rate limit reached." They will be picked up by the next day's run, prioritized (Section 6.4).

### 6.4 Prioritization when the rate limit is reached

If the previous day's run failed to update some assets due to rate limits, the next day's run processes those assets **first** (in the order they were skipped), so they catch up. This is implemented via a small `LastPriceUpdateAttempt` tracking table; the implementation detail is left to the technical spec derivation, but the requirement is recorded here.

---

## 7. FX rate fetching

### 7.1 At lot creation time (Spec D03 §4 step 4)

When the user records a purchase or sale:

1. The data service is asked `get_historical_rate(asset.quote_currency, portfolio.base_currency, purchase_date)`.
2. The data service first checks `FxRateHistory` for an existing row.
3. If found → use the stored value, mark `fx_rate_origin = auto` on the lot.
4. If not found → call the FX provider (Frankfurter). On success, persist to `FxRateHistory` and use the value. On failure, the lot is **still created** but with `fx_rate_at_purchase = NULL` and `fx_rate_origin = manual_pending`; the user is informed and prompted to enter the value manually (per Spec D04 §7.1 case 2).

### 7.2 Current FX rate (for valuation and KPIs)

The "current" FX rate is the most recent rate published by the provider (typically today's, or yesterday's on non-business days). It is requested at the moment the FX engine runs (Spec D04 §11). Specifically:

- The data service calls `get_current_rate(asset.quote_currency, portfolio.base_currency)`.
- The result is **persisted** in `FxRateHistory` with `as_of_date = the rate's publication date as returned by Frankfurter`. This way subsequent calls within the same day for the same pair read from the database, not from the provider.
- If the FX provider call fails, the calculation that needed it surfaces a "datos no disponibles" error per §4.3.

### 7.3 Provider downtime

Frankfurter is operationally very reliable (open-source ECB-data mirror), but if it is unreachable, the system reports unavailability per §4.3 and §9. There is no fallback FX provider in v1.

---

## 8. Asset reference data and the "Add asset" flow

When the user is searching for an asset to add (Spec D03 §4 step 1), the typeahead calls `search_assets(query)` on the active provider. Results are presented to the user; on selection, the system:

1. Verifies that an `Asset` exists for the chosen ticker; if not, creates one with the metadata returned by the provider (`name`, `asset_type`, `quote_currency`, `market`).
2. Verifies that the FX pair from `quote_currency` to the target portfolio's `base_currency` is supported (`FxDataProvider.is_pair_supported`). If not, the asset addition is **rejected** with a clear error: *"Esta moneda no se puede convertir a {base_currency} con el proveedor de cambio actual. No se puede añadir el activo a esta cartera."* (Spec D04 §7.1 case 1).
3. Proceeds with lot creation.

Searches are not persisted or cached in v1 — the typeahead always queries the live provider.

---

## 9. User-visible error handling

Per the project owner's explicit decision (§4.3 and §7), when a provider call fails:

- The relevant UI element shows **"datos no disponibles"** (translated via Spec D08) with the timestamp of the last successful update for that data, when known.
- The UI does **not** silently fall back to old data presented as if it were current. The user always knows the difference between "the latest data" and "the latest data we successfully got, which is from N days ago."
- The user can attempt the action again later. There is no automatic background retry of failed user-facing calls in v1.

For the daily job, failures are logged (not user-visible directly). The user only notices indirectly: their indicators don't change that day. This is consistent with the project owner's swing-trading use case where day-to-day update gaps are not critical.

---

## 10. Authorization

External data (historical prices, FX rates) is not per-user — it is reference data shared across the whole system. Any authenticated user can read any `AssetPriceHistory` row for any asset that appears in their own holdings (consistent with Spec D05 §9 for indicator snapshots).

API keys for providers are server-side only and never exposed to the frontend or to API responses. Per Spec 00b §3, they are loaded from environment variables.

---

## 11. Cross-spec consistency

| Other spec | Touch point | This spec's role |
|---|---|---|
| D03 §3.1 (Asset creation) | When the user adds an asset, this spec's `search_assets` populates the typeahead and provides metadata for the `Asset` row. |
| D03 §4 step 4 (Lot FX) | This spec's `get_historical_rate` is the source of `fx_rate_at_purchase`. |
| D03 §11 (FX pair unsupported) | This spec's `is_pair_supported` is what enforces the pre-creation rejection. |
| D04 §7 (FX missing/unsupported) | This spec defines how unavailability is detected and propagated. |
| D04 §11 (current FX rate) | This spec's `get_current_rate` is the source. |
| D05 §6.1 (daily indicator job) | This spec defines the data fetch the job depends on. |
| D05 §6.1 "insufficient data" | If the provider hasn't returned 200 days for an asset (newly listed, error gap), MA200 is silently skipped per D05. |
| D06 §5.5 (alert engine within the daily job) | This spec's job triggers the alert engine after each asset's prices are updated. |

---

## 12. Configuration keys (added to Spec 00f)

| Key | Type | Default | Description |
|---|---|---|---|
| `market_data.provider` | enum (`twelve_data` \| `finnhub`) | `twelve_data` | The active market data provider. |
| `market_data.twelve_data.base_url` | string | `https://api.twelvedata.com` | Base URL for the Twelve Data API. Configurable for testing/mocking. |
| `market_data.twelve_data.daily_call_budget` | integer | `800` | The known daily rate-limit ceiling. Used by the prioritization logic in §6.4 to know when to stop gracefully. |
| `market_data.finnhub.base_url` | string | `https://finnhub.io/api/v1` | |
| `market_data.finnhub.per_minute_call_budget` | integer | `60` | The known per-minute rate-limit ceiling for Finnhub free tier. |
| `fx_data.provider` | enum (`frankfurter`) | `frankfurter` | The active FX provider. Only `frankfurter` is supported in v1. |
| `fx_data.frankfurter.base_url` | string | `https://api.frankfurter.dev/v2` | Base URL for Frankfurter. |

Spec 00e (Prerequisites & Manual Setup) is updated with the two new environment variables:

- `MARKET_DATA_TWELVE_DATA_API_KEY` — obtained free from `https://twelvedata.com`.
- `MARKET_DATA_FINNHUB_API_KEY` — obtained free from `https://finnhub.io`.

Frankfurter requires no API key; nothing to add there.

At minimum, the API key for the **currently active market data provider** must be set. The other may remain unset.

---

## 13. Out of scope for v1

- **Multiple market data providers active simultaneously** (e.g. consensus checking or fallback chain). One active provider at a time.
- **Intraday updates** between scheduled job runs. Indicators and prices refresh at most once a day in v1.
- **Real-time price streaming** (WebSocket). Out of scope.
- **Provider-side webhooks or push notifications** of price changes.
- **Adjustments for corporate actions** (splits, dividends affecting share counts) at the data layer. Asset prices come from the provider as published; the user records corporate actions manually per Spec D03 §11.
- **Storage of intraday tick data**. Only daily closes are stored.
- **Cross-provider data quality reconciliation** (detecting and alerting when Twelve Data and Finnhub disagree about a date). Out of scope; the active provider's value wins.
- **Caching responses in Redis on top of database persistence.** The database itself functions as the cache; adding a separate hot cache is unjustified at MVP scale.
- **Automatic switching to the backup provider when the active one fails.** Manual configuration change only.
- **Detection and re-fetching of provider-side data corrections** (§5.3). Stored values are treated as the source of truth once written.

---

## 14. Rationale

The adapter pattern across both market and FX data, combined with the configuration-driven provider selection, makes this the third specification in the project (after Spec D07 for LLM and the broader portability theme) to treat external integrations as **pluggable**. This is intentional: free-tier API providers have a history of changing terms, going down, or being acquired. The cost of writing two adapters today is significantly lower than the cost of an emergency provider migration that touches business logic months from now.

Persisting historical data in the local database, and never overwriting it once written, gives the system two properties that matter for an academic deliverable and for the user's trust:

- The system is largely **functional offline**, after first fetch: it can compute indicators and KPIs on already-fetched data without further provider calls.
- The user's reported financial history is **stable**: no silent updates from upstream data corrections, no flickering numbers, no "yesterday I had a 12% gain but today it's 11.7% and I don't know why."

The "no fallback to stale data" policy at the user-facing call level (§4.3, §9) is a clear application of the project's broader principle of preferring **explicit failure** over **silent approximation**, already seen in D04 (no triangular FX), in D05 (no zero-fallback for insufficient history), and now here. The user can tell the difference between "the system is working" and "the system is degraded" without having to read the technical details.

The decision to support both Twelve Data and Finnhub in v1 — rather than just one — costs marginally more code (one extra thin adapter) but removes a known-fragility risk: if the chosen provider's free tier changes terms, the project owner can switch with a configuration edit and a restart. This is the same risk-management thinking applied to Spec D07 for LLM providers.

The known operational limit (~400 assets at full daily refresh) is documented rather than hidden because hiding it would be a disservice to whoever inherits the project. It is not a v1 problem — it is a problem for "later," and it now has a name.
