# Changeset C14 — Fall Back to Last Known Price on Live Fetch Failure + Show Fetch Timestamp

**Status:** Implemented
**Type:** Cross-spec changeset (requirement change, project owner reviewed live behavior)
**Triggered by:** Project owner reviewed the asset detail screen for two real holdings (IAG on BME, INTC on NASDAQ) and found the "Precio actual" card showing **"No disponible"** even though the asset has a full price history. Root cause: the on-demand price endpoint calls the live market data provider synchronously and, per Spec D09 §5.4/§9, raises a hard error with nothing shown when that live call fails (rate limit, provider outage, ticker temporarily unsupported) — even though a perfectly usable last-known price already sits in `AssetPriceHistory` from the daily job.
**Affects implementations of:** Spec D09 (Market & FX Data Integration) §5.4, §9; Spec D10 (frontend architecture).

---

## 0. How to read this document

Spec D09 §9 currently states, explicitly and deliberately: *"The UI does not silently fall back to old data presented as if it were current. The user always knows the difference between 'the latest data' and 'the latest data we successfully got, which is from N days ago.'"* That was not an oversight — it was the v1 design decision, enforced by making `GET /market-data/assets/{ticker}/price` raise a 503 on any provider failure with no fallback.

This changeset **reverses that decision for the on-demand current-price endpoint only**, per explicit project owner instruction: keep the last known value instead of showing an error, and always show *when* that value is from. This is the same pattern as Changeset C13, which reversed a different explicit D07 decision after direct product feedback — recorded as a changeset per this project's Spec Driven Development discipline (Spec 00a), not a silent code change.

The daily job (D09 §6) and its "does not silently fall back" framing for logged failures are **unchanged** — this changeset only touches the single on-demand lookup path used by the asset detail screen and the price-level form.

---

## 1. What actually changes, and what does not

**Changes:**
- `GET /market-data/assets/{ticker}/price` — when the live provider call raises `ProviderError`, the endpoint now looks up the most recent `AssetPriceHistory` row for that asset and returns it instead of a 503. A 503 is only raised when there is *no* stored price at all (brand-new asset, never successfully priced).
- The response gains `fetched_at` (UTC timestamp): `now()` for a genuinely live value, or the stored row's own `fetched_at` (when the daily job actually wrote it) for a fallback value. This is the "hour of execution" the project owner asked to see next to the date, and it is also how staleness stays visible without a hard error — reading "10 jul 2026, 02:03" next to a card while today is later already tells the user this isn't a live-this-second quote, honoring the spirit of D09 §9 without reintroducing the hard failure.
- `frontend/src/screens/asset-detail-screen.ts` renders that timestamp (date **and** time, via the existing `formatDateTime` util) under "Precio actual" instead of the previously unformatted bare date string.

**Does not change:**
- The daily job (D09 §6) — still fetches and persists `AssetPriceHistory` exactly as before; this changeset only changes what the on-demand endpoint does when a *live* call fails.
- `MarketDataService.get_current_price()` itself is untouched — it still either returns a live `PricePoint` or raises `ProviderError`. The fallback lookup lives in the API layer (`app/api/market_data.py`), which already owns the DB session dependency, mirroring where `summary_service.py` does the same last-known-price lookup for portfolio totals (Changeset C08). No new pattern is introduced.
- `search_assets` and `get_current_fx_rate`/FX endpoints — out of scope, still fail hard on a provider error exactly as documented in D09 §7.3/§9. Only the asset current-price endpoint is affected.
- `frontend/src/screens/set-levels-screen.ts` — no code change needed there; it already calls the same endpoint and silently treats a thrown error as "no default price to prefill." It benefits automatically: a last-known price is now returned instead of an exception, so the price-level form gets a sensible default even when the live provider is briefly down.

---

## 2. Backend — API endpoint fallback

### Where in code

- `backend/app/api/market_data.py` — `get_asset_price()`:
  - Add `db: AsyncSession = Depends(get_db)` to the handler.
  - On `ProviderError` from `svc.get_current_price(...)`, call a new local helper `_last_known_price(db, ticker)` that:
    1. Looks up `Asset` by `ticker` (globally unique — `backend/app/db/models/asset.py`).
    2. Returns the `AssetPriceHistory` row with the highest `as_of_date` for that `asset_id`, or `None` if the asset has no history or does not exist.
  - If a fallback row is found, return it (see §3 for the response shape). If not, raise the existing `_unavailable(exc)` 503 exactly as today.
  - On a successful live fetch, `fetched_at` is set to `datetime.now(UTC)` — the moment of this request's execution, not derived from the provider response (providers don't return a "fetched at" field).

### Why the fallback lives in the API layer, not `MarketDataService`

`MarketDataService.get_current_price()` has no `db` parameter and is used by other on-demand callers (`fx_calc.py`) that have their own fallback semantics already (e.g. `fx_calc.py` treats a missing current price as "use the value the user typed in the form"). Adding a DB-touching fallback inside the service would change behavior for those callers too, silently. Keeping it in the endpoint scopes the change precisely to the one UI surface the project owner reviewed (`GET .../price`), same reasoning `summary_service.py` already used to justify its own direct `AssetPriceHistory` reads instead of going through the service (see that file's module docstring).

---

## 3. Backend — response schema

`PricePointResponse` (`backend/app/api/d09_schemas.py`) gains:

| Field | Type | Notes |
|---|---|---|
| `fetched_at` | `datetime` (UTC) | Execution timestamp: `now()` for a live value, or the stored row's `fetched_at` for a fallback value. Always present — this is what the frontend renders next to the price. |

`as_of_date` and `price` are unchanged in meaning. No new "is this stale" boolean is added: showing the actual timestamp is the transparency mechanism (per §1 above), and adding a second, redundant flag would duplicate what the timestamp already communicates — consistent with this project's simplicity-first convention (Spec 00a).

### Acceptance criteria

- Live provider call succeeds → `fetched_at` is within the same second as the request, `as_of_date` is the provider's trading day.
- Live provider call fails (`ProviderError` of any kind) and `AssetPriceHistory` has at least one row for the asset → 200 response with the latest stored `close_price`/`as_of_date`, and `fetched_at` equal to that row's own `fetched_at` (i.e. when the daily job actually captured it, which may be days in the past).
- Live provider call fails and the asset has zero stored price history → 503, exactly as before this changeset (no behavior change for a genuinely never-priced asset).

---

## 4. Frontend — `pi-asset-detail-screen`

### What changes

- `_load()` now stores `priceResult.value.fetched_at` (instead of `as_of_date`) into a renamed field, and no longer discards it on a settled-but-still-empty response.
- `_renderDetail()` renders that timestamp with `formatDateTime()` (`frontend/src/utils/format.ts`, already used elsewhere — `dateStyle: 'medium', timeStyle: 'short'`) instead of printing the raw ISO date string directly. This is what produces "10 jul 2026, 08:03" instead of the current unformatted "2026-07-10" seen in the reported screenshot.
- "No disponible" (`screen.asset.price_na`) is still rendered exactly as before, but now only appears for an asset with **zero** stored price history ever — the case the 503 still covers.

### Where in code

`frontend/src/screens/asset-detail-screen.ts` (`_load()` lines ~93-96, `_renderDetail()` line ~315), `frontend/src/api/market-data.ts` (`PricePoint` interface gains `fetched_at: string`).

### Acceptance criteria

- Asset with a live-available price: card shows the price and "10 jul 2026, 08:03"-style date+time, matching the moment the screen was loaded.
- Asset whose live provider call fails but has prior history (the IAG/INTC screenshots): card shows the last known price instead of "No disponible", with the date+time of when that price was actually captured (which may be a past day).
- Brand-new asset with no price history at all and a failing live call: card still shows "No disponible" (unchanged edge case).

---

## 5. Order of implementation

1. `backend/app/api/d09_schemas.py` — add `fetched_at` to `PricePointResponse`.
2. `backend/app/api/market_data.py` — `db` dependency, `_last_known_price()` helper, fallback branch in `get_asset_price()`, `fetched_at` on the live-success branch.
3. `frontend/src/api/market-data.ts` — `PricePoint.fetched_at`.
4. `frontend/src/screens/asset-detail-screen.ts` — store and render `fetched_at` via `formatDateTime()`.
5. Manual verification (per Spec 00c §2/§3 — this is a DB+provider-touching integration path, verified manually rather than with a new automated test, consistent with `summary_service.py`'s and Changeset C04's precedent): run locally, force a provider failure (e.g. temporarily unset the market data API key or use an unsupported ticker) and confirm the fallback renders instead of "No disponible".
6. Deploy to Azure (no schema/migration change — `AssetPriceHistory` is read-only in this changeset, no new columns).

---

## 6. What this changeset does not change

- `AssetPriceHistory` / `FxRateHistory` schemas — no migration needed, purely additive at the API response level.
- The daily update job (`run_daily_update` / `_run_daily_update_cascade`) — unchanged.
- FX rate endpoints and `search_assets` — still fail hard on provider error, per D09 §7.3/§9, unchanged.
- `set-levels-screen.ts` and `price-level-form.ts` — no code changes; they inherit the fallback for free through the shared endpoint.

## 7. Out of scope of this changeset

- An explicit "stale"/"cached" visual badge beyond the timestamp itself (see §3's rationale for why this is intentionally left out).
- Retrying the live provider automatically before falling back (still a single attempt, per D09 §4.3's existing retry/backoff scope, unchanged).
- Applying the same fallback to FX rates or asset search — not reported as broken, not requested, left for a future changeset if it becomes a real problem.

---

## 8. Rationale

Spec D09 §9's "never silently fall back" rule was written to protect against a specific failure mode: showing a stale number *as if it were live* with no way to tell the difference. In practice, once the daily job has been running for a while, "no data at all" (the only alternative the old design offered) is strictly worse for the user than "the last real price we have, clearly timestamped" — the project owner's direct feedback on seeing "No disponible" for assets that plainly have history confirms this. Showing the fetch timestamp preserves the original spec's transparency goal through a different, less disruptive mechanism than a hard error, which is why this changeset amends rather than deletes that section's intent.
