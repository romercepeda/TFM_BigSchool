# Changeset C19 — Current Price: Cache-Only by Default, On-Demand Refresh

**Status:** Pending implementation
**Type:** Cross-spec changeset (bug fix — behavior contradicted the spec's own stated design)
**Triggered by:** Project owner reviewed the asset detail screen's "Current Price" card and asked whether it re-fetches live on every visit. It does. He asked for the opposite: don't call the live provider automatically, always show the last known value with its timestamp (unchanged from today), and add a refresh icon on that card so a live check is a deliberate, on-demand action.
**Affects implementations of:** Spec D09 (Market & FX Data Integration) — corrects §5.4 to match this changeset's behavior; Spec D10 (frontend architecture).

---

## 1. What was actually happening (confirmed in code)

Spec D09 §5.4 already stated the intended v1 design: *"Outside the daily job, current prices are not re-fetched on demand in v1."* The implementation never honored this: `GET /market-data/assets/{ticker}/price` (`backend/app/api/market_data.py`) called the live provider synchronously on every request, and `frontend/src/screens/asset-detail-screen.ts` (and `set-levels-screen.ts`, for the define-levels form's price pre-fill) called that endpoint unconditionally on every screen load. Changeset C14 added a fallback to the last known `AssetPriceHistory` row when the live call *failed*, but explicitly left the live-call-on-every-load behavior itself unchanged (see that changeset's §1/§16/§28).

Consequence: every visit to any asset detail page — including navigating away and back — spent one call against the market-data provider's daily quota (Twelve Data free tier: 800 calls/day, D09 §7). This is pure waste for a value that, most of the time, hasn't changed since the last view a minute ago.

## 2. What changes

- The automatic, on-load price lookup becomes **cache-only**: it reads the last known price from `AssetPriceHistory` (written by the daily job, or by a prior manual refresh — §3) and never calls the live provider.
- A **refresh icon** (↻) appears next to the "Current Price" label on the asset detail screen. Clicking it triggers exactly one live provider call for that single asset, on demand, updating the card in place — same "price + fetched-at timestamp" presentation as today, just user-triggered instead of automatic.
- No other screen gains a refresh control. `set-levels-screen.ts`'s price pre-fill also becomes cache-only as a side effect of reusing the same endpoint — acceptable, since it was already designed to degrade gracefully to `null` on any price-lookup failure (see `set-levels-screen.ts` lines ~46-55).

## 3. Backend — endpoint split

`backend/app/api/market_data.py`:

- `GET /market-data/assets/{ticker}/price` — **changed**. No longer calls `MarketDataService.get_current_price()`. Now only calls the existing `_last_known_price(db, ticker)` helper (introduced in C14) and returns that row. Raises 503 only when no price has ever been stored for the asset (unchanged edge case from C14, just reached more often now that live calls aren't implicit).
- `POST /market-data/assets/{ticker}/price/refresh` — **new**. Contains exactly the logic the GET endpoint used to have: live call via `MarketDataService.get_current_price()`, falling back to `_last_known_price` on `ProviderError`, 503 only if there's no live value *and* no stored value. Requires the same `holding.view` permission as the GET — refreshing what you can already see doesn't need a stronger permission.
- Per D09 §5.3 (immutability of stored historical data), the refresh endpoint's result is **not** written to `AssetPriceHistory` — it's a transient value shown with its own `fetched_at`, same as the live branch always was. The daily job remains the sole writer of that table.

## 4. Frontend

- `frontend/src/api/market-data.ts` — `getAssetPrice()` now hits the cache-only GET (no signature change). New `refreshAssetPrice(ticker, exchange?)` posts to the refresh endpoint.
- `frontend/src/screens/asset-detail-screen.ts`:
  - New `_priceRefreshing` boolean state.
  - New `_doRefreshPrice()`: guards against double-clicks, calls `refreshAssetPrice`, updates `_currentPrice`/`_priceFetchedAt` on success, silently keeps the previous value on failure (no new error UI — the existing "no disponible" / stale-timestamp treatment already communicates staleness).
  - "Current Price" card gains a `.refresh-icon-btn` (↻, same visual language as `analysis-screen.ts`'s existing `.edit-icon-btn`) with a `.spinning` CSS animation while the request is in flight.
- `frontend/src/i18n/locales/{es,en}.json` — new key `screen.asset.refresh_price` ("Actualizar precio" / "Refresh price"), used as the button's `title`.

## 5. Spec D09 correction

§5.4 is corrected in a follow-up edit to this spec to state the behavior as it now actually is: current prices are fetched by the daily job (persisted) or by this changeset's explicit on-demand refresh (transient, not persisted) — never implicitly on page load. The stale cross-reference to a non-existent "Section 8" discussion is also removed.

## 6. Where in code

1. `backend/app/api/market_data.py` — split `get_asset_price` into cache-only GET + new `refresh_asset_price` POST.
2. `frontend/src/api/market-data.ts` — `refreshAssetPrice()`.
3. `frontend/src/screens/asset-detail-screen.ts` — refresh button, state, handler, CSS.
4. `frontend/src/i18n/locales/es.json`, `en.json` — `screen.asset.refresh_price`.
5. `specs/domain/spec-d09-market-fx-data-integration.md` §5.4 — corrected.
6. Manual verification via Playwright (per `.claude/skills/verify-playwright`) — no new pytest integration suite added, consistent with this project's existing practice of verifying DB/provider-touching endpoint paths manually rather than with a `TestClient` + test-DB harness (see e.g. `test_settings_api.py`'s own docstring: "DB-touching paths... verified manually against the real dev database").
7. `frontend/src/version.ts` — patch bump on publish, per [[feedback-app-versioning]].

## 7. What this changeset does not change

- The daily job itself (D09 §6) — unchanged, still the sole writer of `AssetPriceHistory`.
- FX rate lookups (`GET /market-data/fx/rate`) — that endpoint already has its own DB-cache-first behavior (D09 §7.1) and isn't touched.
- The asset-search typeahead (`GET /market-data/assets/search`) — intentionally always live (D09 §8), unrelated to this changeset.
- Changeset C14's fallback semantics — reused as-is inside the new refresh endpoint, not altered.

## 8. Out of scope

- A "refresh all holdings" bulk action — the project owner asked for a per-asset control only; "Run daily update" in Settings already covers the bulk case.
- Rate-limiting or debouncing repeated manual refresh clicks beyond the simple in-flight guard (`_priceRefreshing`) — not requested, and the user is the one spending their own provider quota deliberately by clicking it.
