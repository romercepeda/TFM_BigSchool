# Spec D12 — Multi-Provider Cascade for Market & FX Data

**Status:** Approved
**Type:** Domain capability (evolution of D09)
**References:** Spec D09 (Market & FX Data Integration), Spec D05 (Indicator Catalog), Spec D06 (Alert Engine), Spec D10 (Frontend), Spec D11 (Roles & Permissions), Spec 00b (Security Practices), Spec 00e (Prerequisites), Spec 00f (Global Configuration)

---

## 1. Purpose

Evolve the single-active-provider model of D09 into an **ordered cascade of providers**, so that if the first provider cannot deliver data for an asset (rate limit, unknown ticker, downtime, malformed response), the system automatically retries with the second, then the third, and so on. Assets that fail with every provider in the cascade are surfaced to the user as an explicit list of "not found in any provider" errors.

This spec also introduces **EODHD** as a new market data provider, chosen specifically because its free tier covers European exchanges (BME, Xetra, Euronext, LSE) that were verified during the D09 audit as unreliable in Finnhub's free tier.

The cascade applies to both market data and FX data. In v1, only one FX provider (Frankfurter) is implemented, but the architectural mechanism is the same so that adding a second FX provider later is a configuration change.

---

## 2. Conceptual model

Three concepts, distinct from D09:

1. **Provider list** — an ordered list of provider codes, editable in Settings by an administrator. First provider is tried first; the last is the last resort.
2. **Cascade execution** — for any batch operation (typically the daily job), the system iterates over the ordered list, calling each provider only for the subset of assets that the previous providers did not resolve. State does not persist between runs: every daily job restarts from the first provider (per project owner's explicit "keep it simple" decision).
3. **Cascade failure report** — the list of assets that no provider in the cascade could resolve. Surfaced to the user via the header notification system already defined in D07 §10 and D10 §8.

The single-active-provider selector of D09 (`market_data.provider`) is **replaced** by a list. Changeset C04 covers this replacement without rewriting D09.

---

## 3. Providers added or reaffirmed in v1

| Provider | Type | Free tier (as verified 2026) | Coverage | Notes |
|---|---|---|---|---|
| Twelve Data | Market data | 800 API calls/day, 4-hour delay | US + European markets included in free tier | Continues as default first-in-list, per D09. |
| **EODHD** (new in D12) | Market data | 20 API calls/day, 1-year historical depth | US + full European market coverage (BME, Xetra, Euronext, LSE) confirmed in free tier | Suggested as second-in-list; low rate limit means it is best used as a fallback rather than a primary. |
| Finnhub | Market data | 60 API calls/minute | US-only in free tier (European markets require paid Premium — clarified in Changeset C03) | Suggested as third-in-list where relevant, or omitted entirely for portfolios with only European assets. |
| Frankfurter | FX data | Unlimited, no key required | ECB reference rates; all v1 base currencies | Only FX provider in v1; kept as a single-element list for architectural symmetry. |

The default cascade order shipped with a fresh install is: `market_data.providers: [twelve_data, eodhd, finnhub]` and `fx_data.providers: [frankfurter]`. The administrator can reorder or remove entries via the Settings screen (§7).

---

## 4. The adapter contract (unchanged)

The `MarketDataProvider` and `FxDataProvider` interfaces defined in D09 §4.1 and §4.2 are **unchanged** in shape. The addition is:

- A new concrete adapter `EODHDProvider` implementing `MarketDataProvider`.
- A new module `providers/cascade.py` that iterates over the ordered list at the layer above the adapters. Individual adapters remain provider-agnostic and know nothing about being part of a cascade.

The `EODHDProvider` normalizes EODHD-specific quirks:

- **Ticker format**: EODHD uses `<SYMBOL>.<EXCHANGE_CODE>` (e.g. `SAN.MC` for Santander on Madrid, `AIR.PA` for Airbus in Paris, `SAP.XETRA` for SAP on Xetra, `BP.LSE` for BP in London). The adapter maintains a lookup table mapping the exchange codes we use internally to EODHD's convention. When our internal exchange representation differs from EODHD's, the adapter is the sole place that knows the mapping.
- **Historical depth**: the free tier is limited to 1 year of historical data. The adapter reports a `provider_max_lookback_days` constant of `365`; the cascade layer uses this to decide whether to even try EODHD for a request that needs deeper history (see §5.3).
- **Rate limit tracking**: 20 calls/day is very tight. The adapter maintains an in-memory counter of calls consumed in the current UTC day and raises `RateLimitError` proactively when the budget is about to be exhausted, before actually hitting the provider (to avoid wasting the very last calls on the retry itself).
- **Response quirks**: EODHD returns dates as strings in `YYYY-MM-DD` format; adjusted vs raw close is a separate field; the adapter always uses the split-and-dividend-adjusted close for consistency with what Twelve Data returns.

---

## 5. Cascade execution

### 5.1 Cascade for the daily job

The daily job (Spec D05 §6.1, Spec D09 §6) now executes as follows for each execution:

1. Compute the set of assets that need updating (all assets in non-archived holdings).
2. Load the configured cascade list from Settings.
3. **Round 1 — try provider `providers[0]` for all assets.** For each asset:
   - If success → persist to `AssetPriceHistory` per D09 §5.1 with `provider = providers[0]`.
   - If failure (any reason) → keep the asset in the "unresolved" set.
4. **Round 2 — try provider `providers[1]` for the unresolved subset only.** Same success/failure logic.
5. Continue with `providers[2]`, `providers[3]`, etc. until either every asset is resolved or the list is exhausted.
6. **Any assets still unresolved at the end** are collected into a `CascadeFailureReport` (§6). Their indicators are not computed for that day (consistent with D05 §6.1 "insufficient data → silently skipped"). Their alert levels are not re-evaluated for that day either.
7. The report is delivered as a header notification to any user who owns any of the failed assets (§6.2).

### 5.2 Cascade for FX

The same pattern applies to FX rate fetching (D09 §7). The cascade list is `fx_data.providers`. In v1, this list has one element (`frankfurter`), so the cascade degenerates to the single-provider behavior of D09.

Adding a second FX provider in the future is a matter of writing the adapter and adding it to the list — no code change beyond the adapter.

### 5.3 Cascade with heterogeneous provider capabilities

Providers have different capabilities (e.g. EODHD's 1-year lookback vs Twelve Data's much longer history). The cascade layer must handle this gracefully:

- When a provider's `provider_max_lookback_days` is less than the depth required by the request (e.g. the daily job requests 250 days to feed MA200), that provider is **skipped for that request** without consuming an API call. It is not counted as a "failure" for the asset; the asset moves to the next provider directly.
- If **all** providers in the cascade lack sufficient lookback for a specific asset, the asset is reported in the `CascadeFailureReport` with reason `insufficient_lookback` (distinct from `not_found` or `rate_limited`).

This means EODHD in v1 is only useful as a fallback for **incremental daily updates** (which need 1-2 days of new data), not for **bootstrapping a newly added asset** (which needs 200+ days). This limitation is documented for the user in Settings when EODHD is placed anywhere but last, so the operator understands the trade-off.

### 5.4 No cross-run memory

Per project owner decision: the cascade does **not** remember which provider succeeded for which asset on the previous run. Every daily job starts from `providers[0]` again. Rationale: state adds bugs, and this is a personal-use system where the extra API calls to re-try the first provider are affordable.

If in the future the API budget becomes a real constraint, an "asset-to-preferred-provider" cache is a natural additive change that does not break this spec.

### 5.5 Search uses only the first provider

Per project owner decision: asset search (Spec D09 §8, `search_assets(query)`) always calls **only the first provider** in the cascade list. If the first provider returns no results, the user is told "No results found" — the search does not silently fall back to the second provider.

Rationale: search results power the "Add asset" flow, and every added asset becomes part of the daily job's cascade. Mixing search results across providers would surface asset identifiers (tickers, exchange codes) in different conventions, confusing the user. Standardizing on the first provider's identifiers keeps the UX predictable.

---

## 6. `CascadeFailureReport`

### 6.1 Content

A `CascadeFailureReport` is generated at the end of every daily job execution. Its structure:

```json
{
  "run_id": "uuid",
  "run_completed_at": "2026-11-14T02:04:12Z",
  "total_assets_processed": 42,
  "resolved_by_provider": {
    "twelve_data": 38,
    "eodhd": 3
  },
  "failures": [
    {
      "asset_id": "uuid",
      "ticker": "MYSTOCK.XY",
      "reason": "not_found | rate_limited | insufficient_lookback | provider_error",
      "providers_tried": ["twelve_data", "eodhd", "finnhub"],
      "last_error_by_provider": {
        "twelve_data": "symbol_not_found",
        "eodhd": "symbol_not_found",
        "finnhub": "unauthorized_for_european_market"
      }
    }
  ]
}
```

The report is persisted (`cascade_failure_reports` table) so historical failures can be inspected. Successful runs may or may not persist an empty report; the implementation chooses whichever is more useful for debugging — an empty report is not user-visible.

### 6.2 Delivery to users

Failures are delivered via the header notification system defined in D07 §10 and D10 §8:

- Each affected user (owner of one or more failed assets) sees a new notification: *"N of your assets could not be updated today. View details."*
- Clicking opens a modal listing exactly which of **their own** assets failed and why. The user does not see other users' failures.
- Admin users see, in addition, a link to the full cross-user report from the Administration section (§7.4).

### 6.3 Retention

`CascadeFailureReport` rows are retained for 30 days by default, then hard-deleted by a small cleanup job. The retention is configurable via `market_data.failure_report_retention_days` (§9). This is not part of the audit log; it is operational data.

---

## 7. Settings UI — the "Data providers" section

### 7.1 Location and visibility

A new section **"Data providers"** is added to the Settings screen (Screen 11 in D10), visible only to users whose effective permissions include `system.view_config` (per D11 §5.1, an administrator-only permission in v1).

Users without this permission see no trace of this section — not even a message. It is not merely disabled; it does not render at all (consistent with D11 §7.1 defense-in-depth pattern).

### 7.2 Provider list controls

The section displays two sub-lists: **Market data providers** and **FX data providers**. Each list shows the currently configured cascade order.

For each list:

- Drag-and-drop to reorder the entries.
- A remove button next to each entry (removes it from the cascade; the provider adapter still exists in code, just not used).
- An add button to re-introduce an available adapter that is not currently in the list.
- A "Reset to defaults" button that restores the shipped default order (§3).

Changes persist immediately on save. The next daily job execution uses the new order. There is no confirmation dialog for reordering; there is one for removing all providers from a list ("This will disable all market data updates until you add a provider back — continue?").

### 7.3 API key visibility (read-only in v1)

For each provider that requires an API key (Twelve Data, EODHD, Finnhub), the section displays:

- The provider's display name.
- Its current API key **masked** (e.g. `••••••••abc123` showing only the last 6 characters), or the literal string *"Not configured — set `MARKET_DATA_XYZ_API_KEY` in `.env` and restart"* if not set.
- A short help text: *"API keys are managed via environment variables per Spec 00b for security and portability. To change a key, edit `.env` and restart the backend."*

The API key values themselves are **not editable** from the UI in v1. This is deliberate per project owner decision: keeps the secret-management model consistent (all secrets in environment variables), avoids introducing encryption-at-rest infrastructure just for API keys, and matches the operational cadence of key rotation (very infrequent).

Frankfurter does not require an API key; its entry omits this section.

### 7.4 Failure report access

An additional read-only view **"Cascade failure report"** is available to administrators from the same section, showing the last 30 days of failed-asset entries across all users. Filtering by date, provider, or reason. Purely informational — no actions.

---

## 8. Cross-spec impacts

| Other spec | Impact |
|---|---|
| **D09 §3.1** | The single `market_data.provider` key is deprecated in favor of `market_data.providers` (list). The single-provider model is replaced by the cascade. Handled in Changeset C04. |
| **D09 §5.1** | `AssetPriceHistory.provider` gains one more allowed value: `eodhd`. |
| **D09 §6** | The daily job description is extended per §5.1 above. |
| **D09 §7** | FX fetching uses the cascade pattern, even though the list has one entry in v1. |
| **D09 §8** | Search uses only the first provider (§5.5). |
| **D10 §route table** | No new routes; the "Data providers" section lives inside `/settings`. |
| **D11 §5.1** | The permission `system.view_config` gates access to the section. No new permission is added. |
| **D07 §10 / D10 §8** | The header notification system now also carries cascade failure reports for the current user. |
| **00b §3 / 00e §6** | API key policy unchanged: env vars only. No new env var beyond EODHD's (§10). |
| **00f** | New config keys under `market_data.providers` (list), `fx_data.providers` (list), and `market_data.failure_report_retention_days` (§9). |

---

## 9. Configuration keys (added to Spec 00f via Changeset C04)

| Key | Type | Default | Description |
|---|---|---|---|
| `market_data.providers` | list of provider codes | `["twelve_data", "eodhd", "finnhub"]` | Ordered cascade of market data providers. First is tried first. Editable from Settings by admins. Replaces the deprecated singular `market_data.provider`. |
| `fx_data.providers` | list of provider codes | `["frankfurter"]` | Ordered cascade of FX providers. Editable from Settings by admins. In v1 only Frankfurter is implemented. |
| `market_data.failure_report_retention_days` | integer ≥ 1 | `30` | How many days of cascade failure reports to retain before cleanup. |
| `market_data.eodhd.base_url` | string | `https://eodhd.com/api` | Base URL for the EODHD API. |
| `market_data.eodhd.daily_call_budget` | integer | `20` | Known daily rate-limit ceiling for EODHD free tier. Used by the adapter for proactive rate-limit avoidance (§4). |
| `market_data.eodhd.max_lookback_days` | integer | `365` | EODHD free tier historical depth in days. Used by the cascade layer per §5.3. |

The existing keys `market_data.twelve_data.*`, `market_data.finnhub.*`, and `fx_data.frankfurter.*` from D09 §12 are **unchanged**.

The deprecated key `market_data.provider` remains readable for one release for backward compatibility: if it is present and `market_data.providers` is not, the loader builds a single-element list from it and logs a deprecation warning. The next major release removes this compatibility shim.

---

## 10. Environment variable added (via Changeset C04, per Spec 00e)

- `MARKET_DATA_EODHD_API_KEY` — obtained free from `https://eodhd.com`. Free tier: 20 calls/day.

At minimum, an API key must be set for every provider **present in the cascade** (i.e. in `market_data.providers`). Providers removed from the list may have their keys unset.

At startup, the system validates that for every provider in the cascade lists, its required environment variable is set. If not, startup **fails** with a clear message identifying the missing key and pointing to the Settings-based remediation ("either configure the key in `.env` or remove the provider from the cascade").

---

## 11. Out of scope for v1

- **Persistent memory of "which provider succeeded per asset"** to skip failed providers on subsequent runs (§5.4).
- **Editable API keys from the UI** (§7.3).
- **Multi-search** across all providers simultaneously (§5.5).
- **Per-asset provider override** (the initially considered "each asset chooses its provider" model) — the cascade replaces this, uniformly.
- **Cross-provider price reconciliation** (detecting and alerting when Twelve Data and EODHD disagree about a close for the same date) — noted in D09 §13 already.
- **Historical rewrite when the cascade order changes** — existing `AssetPriceHistory` rows retain their original `provider` value and are not re-fetched.
- **Notification of admins when a provider consistently fails for N days** — the failure report is on-demand; no push escalation.

---

## 12. Rationale

The cascade model is a **strictly additive evolution** of D09's single-active-provider model. It preserves the adapter interface, the persistence model, and the user-facing semantics (still "explicit failure rather than silent approximation"), while removing the operational cliff where switching providers required a config file edit and a restart. In particular, it lets Twelve Data's free tier — which already covers European markets — remain the primary source, while EODHD steps in for the tail of assets or edge conditions where Twelve Data cannot deliver.

The decision to skip cross-run memory is aligned with the project's broader "keep v1 simple; add complexity only when a real need appears" principle. In a personal-use system with a few dozen assets, retrying the first provider daily is not a real cost — 20 calls to Twelve Data before falling to the second-in-list is comfortably within its 800/day budget. If the portfolio ever grows to a size where this becomes a real concern, adding memory is a small additive change that does not break the model.

The read-only API-key display in Settings makes the operator experience visibly consistent — the admin can see at a glance which providers are configured — without inheriting the complexity of encrypted-at-rest secret management. If the operational cadence ever demands runtime key rotation, this can be revisited as a discrete evolution rather than something forced now.

The search-uses-first-provider-only rule prevents a subtle UX pitfall: if a user searches and picks a ticker with EODHD-style notation (`SAP.XETRA`) that Twelve Data does not recognize (`SAP.DE` in Twelve Data's convention), every subsequent daily job would fail the primary provider and rely on the fallback. That is a hidden performance and reliability cost that would confuse the user. Standardizing search on the first provider ensures the ticker chosen aligns with the primary source's conventions.
