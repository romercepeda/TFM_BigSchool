# Changeset C21 — Production Bugfixes: Price Persistence, Xetra Mapping, Post-Login Routing, Login Language Selector

**Status:** Implemented
**Type:** Cross-spec changeset (bug fixes reported directly from production)
**Triggered by:** Project owner reported four issues seen both in production and locally (local running v1.2.0.0): (1) manually refreshing an asset's "Current Price" doesn't stick — the old price reappears after leaving and re-entering the asset; (2) some European stocks (BMW, Mercedes-Benz on Xetra; Mediobanca on Milan/Borsa Italiana) never show a price at all; (3) after login, the app doesn't consistently land on "My Portfolios" as expected; (4) the login screen has a language selector (top-right) that doesn't work and should be hidden.
**Affects implementations of:** Spec D09 §5.3/§5.4 (market data persistence), Spec D12 §4 (EODHD ticker mapping), Spec D01 §6 step 8 and Spec D02 §10 (post-login routing), Spec D10 §6.3.

---

## 1. Current Price refresh not persisted (Spec D09 §5.3/§5.4)

**Root cause:** Changeset C19 deliberately made the manual "refresh price" action (`POST /market-data/assets/{ticker}/price/refresh`) transient — the live-fetched price was shown to the user but never written to `AssetPriceHistory`, reasoning that the table is append-only per D09 §5.3. In practice this meant the refresh only ever updated the frontend's in-memory `_currentPrice` state; navigating away and back re-read the cache-only GET endpoint, which still returned the old stored row.

**Fix:** `MarketDataService.refresh_and_store_current_price()` (`backend/app/services/market_data/service.py`) — resolves the price via the same cascade `get_current_price` uses, then upserts it into *today's* `AssetPriceHistory` row (`ON CONFLICT (asset_id, as_of_date) DO UPDATE SET close_price, provider, fetched_at`, leaving `volume` untouched). This is a narrow exception to §5.3: only today's own row can be corrected this way, by an explicit user action, on the reasoning that a manual refresh is a newer, more authoritative observation than whatever the daily job or an earlier refresh wrote for today. A different day's row is never touched. `POST .../price/refresh` (`backend/app/api/market_data.py`) now calls this instead of the read-only `get_current_price`.

Spec D09 §5.3/§5.4 corrected accordingly.

## 2. Xetra-listed assets (BMW, Mercedes-Benz) failing to fetch a price

**Root cause — confirmed live against both providers, not a guess:** the on-demand current-price cascade (`twelve_data` → `eodhd` → `finnhub`, per `config.yaml`) fails Twelve Data for every non-US symbol on the free tier (confirmed: `BMW:XETR` → HTTP 404 "available starting with the Grow or Venture plan"), so it falls to EODHD. `backend/app/services/market_data/providers/eodhd_ticker_mapping.py` translates the asset's internal `market` field to EODHD's suffix, but its map only had a key of `"XETRA"`. Live queries against Twelve Data's `/symbol_search` (the endpoint that actually populates `Asset.market` when a user adds one of these assets — search always uses the primary/first-in-list provider, D12 §5.5) show it reports Xetra-listed instruments' `exchange` field as **`"XETR"`**, not `"XETRA"`. So `to_eodhd_exchange_code("XETR")` raised `ProviderError` ("No EODHD exchange mapping...") for every Xetra asset, and Finnhub (the last cascade member) explicitly refuses to guess a symbol for any non-US market (`market_data/symbols.py`) — leaving the cascade fully exhausted.

EODHD's own suffix for Xetra was already correct: live calls to `BMW.XETRA` and `MBG.XETRA` both return valid real-time quotes.

**Fix:** `EXCHANGE_TO_EODHD` in `eodhd_ticker_mapping.py` — key corrected from `"XETRA"` to `"XETR"` (value unchanged, `"XETRA"`). `test_eodhd_provider.py`'s parametrized case updated to match. No data migration needed: `Asset.market` for any Xetra asset a user has actually added already stores `"XETR"` (that's what Twelve Data's search returns and what gets persisted verbatim), so this is a pure mapping-key fix.

While investigating, BME (Madrid), Euronext (Paris), and LSE (London) were also verified live against Twelve Data — all three already match the existing map exactly, no other exchange had this bug.

## 3. Mediobanca (Milan / Borsa Italiana) — provider coverage gap, not a mapping bug

Live verification shows this is **not fixable by a mapping fix**: Twelve Data reports Mediobanca's exchange as `"MTA"`, but EODHD's `/exchanges-list` endpoint (checked against the project's actual configured API key) has **no Italy/Milan entry at all** — direct lookups (`MB.MI`, `MB.MIL`, `MB.BIT`) all fail or return empty. Finnhub's free tier has no European coverage either (Changeset C03) and its adapter explicitly refuses non-US symbols.

Three additional free/cheap alternatives were researched and ruled out before accepting this as a known gap:

- **Twelve Data's own paid tiers** — Euronext Milan is listed as a supported exchange on their site, but gated behind the "Pro+/Venture+" plans (not free).
- **Alpha Vantage** — its documentation advertises "BIT (Borsa Italiana)" as a covered exchange with a `.MIL` suffix convention. Tested live against a real free API key the project owner registered: `SYMBOL_SEARCH` for both "Mediobanca" and "Eni" (Milan's most liquid blue-chip, to rule out an obscure-ticker issue) returned **zero Milan-listed results** — only US OTC, London, and Frankfurt cross-listings. The documented exchange support does not reflect actual symbol coverage; free-tier Alpha Vantage does not carry Borsa Italiana data in practice.
- **Marketstack free tier** — 100 requests/*month* (not/day), too restrictive to be a serious candidate regardless of coverage.
- **Stooq** — free and broad European coverage, but no official API/support, ambiguous terms for production/commercial use, and would need an entirely new CSV-based adapter — not pursued.

**Decision (project owner, 2026-07-17):** leave this as a documented gap for now — Mediobanca (and any other Milan/MTA-only-listed asset) will keep returning "Datos no disponibles" until either a paid plan with genuine Italian coverage is contracted, or a cross-listed proxy (e.g. Mediobanca's Frankfurt listing, ticker `ME9`, confirmed live on both EODHD and Alpha Vantage, same instrument/currency but a different trading venue) is explicitly approved as a substitute. No code changes were made for this item.

## 4. Post-login routing (Spec D01 §6 step 8, Spec D02 §10, Spec D10 §6.3)

**Root cause:** the original rule routed differently depending on `portfolios_count` (2+ → My Portfolios, 1 → straight to that portfolio's Dashboard, 0 → Create Portfolio directly) — from the user's perspective this looked like "login sometimes shows a random other page" rather than a predictable landing screen.

**Fix:** `frontend/src/screens/login-screen.ts`'s `_handleResponse()` now always navigates to `/app/portfolios` after login (a pending deep-link redirect via `consumeRedirectAfterLogin()` still takes priority when one is set — that path is unrelated to this bug, it's for a user bounced to `/app/login` from a protected URL). The portfolios list screen already has its own empty-state with a "Create portfolio" CTA, so 0-portfolio users are still one click away from creating their first one. The now-unused `listPortfolios` import was removed from `login-screen.ts`.

Specs D01 §6 step 8, D02 §10, and D10 §6.3 corrected accordingly.

## 5. Login screen language selector — hidden

**Root cause:** the login screen (`frontend/src/screens/login-screen.ts`) had its own `<select id="lang-select">` in the top-right, independent of both the Settings screen's language control and Spec D08 §4, which already states unauthenticated screens render in `i18n.default_language` — there was never a spec basis for a login-time switcher, and the project owner confirmed it doesn't work correctly.

**Fix:** removed the `<select>`, its `.lang` styling, and its `change` listener from `login-screen.ts`, along with the now-unused `currentLanguage` import. The control is gone rather than merely disabled — it had no working effect and no spec-backed reason to exist. This does not touch `currentLanguage` state itself, so it has no effect on whatever language is already active.

## 6. Where in code

1. `backend/app/services/market_data/service.py` — `refresh_and_store_current_price()`.
2. `backend/app/api/market_data.py` — `refresh_asset_price` calls the new service method.
3. `backend/app/db/models/market_data.py` — docstring corrected (append-only *across days*, not within today).
4. `backend/app/services/market_data/providers/eodhd_ticker_mapping.py` — `"XETRA"` key → `"XETR"`.
5. `backend/tests/unit/test_eodhd_provider.py` — parametrized case updated.
6. `frontend/src/api/market-data.ts` — comment corrected (refresh is now persisted).
7. `frontend/src/screens/login-screen.ts` — post-login routing simplified; language selector removed.
8. `specs/domain/spec-d09-market-fx-data-integration.md` §5.3/§5.4, `spec-d01-authentication.md` §6 step 8, `spec-d02-portfolio-management.md` §10, `spec-d10-frontend-architecture.md` §6.3 — corrected.
9. `frontend/src/version.ts` — patch bump on publish, per [[feedback-app-versioning]].

## 7. What this changeset does not fix

- Mediobanca / any Milan (Borsa Italiana, `MTA`)-listed asset — see §3. Accepted as a known gap (project owner decision); needs a paid plan or an explicitly-approved cross-listed proxy to fix, not a code change made here.
- Session restoration / applying `User.preferred_language` on app bootstrap (`main.ts` currently seeds from `navigator.language`, not the persisted user preference, and there is no `GET /auth/me` call on reload) — noticed while investigating the login language selector, but out of scope: the project owner asked only to hide the broken selector, not to fix language persistence across reloads.
