# Changeset C04 — Implement Multi-Provider Cascade & Add EODHD (D12)

**Status:** Implemented
**Type:** Cross-spec changeset
**Triggered by:** Spec D12 (Multi-Provider Cascade for Market & FX Data)
**Affects implementations of:** Spec D09, Spec D05, Spec D07, Spec D10, Spec D11, Spec 00e, Spec 00f

---

## 0. How to read this document

This changeset applies the new capability of D12 to the code implementing D09. As in prior changesets: **do not rewrite D09**. It stays as the historical record of the single-active-provider model. This document lists the code-level deltas required to introduce the cascade and the EODHD provider.

Each change has: what changes, where in code, why, and acceptance criteria.

---

## 1. Add the `EODHDProvider` adapter (D12 §4)

### What changes

Create a new market data adapter for EODHD implementing the existing `MarketDataProvider` interface from D09 §4.1.

### Where in code

- **New file:** `backend/app/market_data/providers/eodhd.py` — the adapter class.
- **New file:** `backend/app/market_data/providers/eodhd_ticker_mapping.py` — the internal-to-EODHD exchange code lookup (e.g. `MADRID → MC`, `XETRA → XETRA`, `EURONEXT_PARIS → PA`, `LSE → LSE`).
- **`backend/app/market_data/providers/__init__.py`**: register `EODHDProvider` in the provider registry alongside `TwelveDataProvider` and `FinnhubProvider`.
- **Unit tests** for the adapter: `backend/tests/market_data/test_eodhd_provider.py` covering happy path, unknown-ticker error, rate-limit proactive check, and the historical-depth `provider_max_lookback_days` constant.

### Why

Per D12 §3 and §4, EODHD is the new provider chosen because Twelve Data's free tier plus Finnhub's free tier do not together give a reliable fallback for European markets, and EODHD does so in its free tier despite the tight 20 calls/day limit.

### Acceptance criteria

- The adapter can fetch a 5-day price series for `SAN.MC` (Santander, BME) and return a normalized `list[PricePoint]`.
- The adapter raises `RateLimitError` before making the 21st call within a single UTC day.
- The adapter exposes `provider_max_lookback_days = 365` as a class-level constant readable by the cascade layer.
- Unit tests pass with mocked HTTP responses simulating EODHD's actual JSON format.

---

## 2. Build the cascade layer (D12 §5)

### What changes

Introduce a new module that sits between the calling code (daily job, FX resolution) and the individual providers. The cascade iterates over the ordered list of providers, calling each one for the subset of items that the previous providers did not resolve.

### Where in code

- **New file:** `backend/app/market_data/cascade.py` — exports `MarketDataCascade` and `FxDataCascade` classes with the iteration logic.
- **`backend/app/market_data/service.py`** (or the equivalent existing service module that D09 introduced): change from calling a single provider to calling the cascade.
- **`backend/app/tasks/daily_job.py`** (the Celery task that runs the daily update): change from calling a single provider to invoking `MarketDataCascade.execute()` and collecting the returned `CascadeFailureReport`.
- **`backend/app/fx/service.py`**: change from calling `FrankfurterProvider` directly to calling `FxDataCascade.execute()`.

### Why

Per D12 §5.1, the cascade is the mechanism that turns "single provider fails → asset skipped" into "single provider fails → try the next one." Without this module, the ordered-list configuration has no runtime effect.

### Acceptance criteria

- Given three mock providers where providers[0] fails for 2 out of 10 assets, providers[1] resolves 1 of those 2, and providers[2] resolves the remaining 1, the cascade returns 10 resolved and 0 in the failure report.
- Given the same setup but providers[2] also fails for the last asset, the cascade returns 9 resolved and 1 asset in the failure report with `providers_tried = [providers[0], providers[1], providers[2]]`.
- The cascade **skips** (does not call) any provider whose `provider_max_lookback_days` is less than the request's required lookback, per D12 §5.3.
- The cascade does **not** persist any state across executions per D12 §5.4.
- Unit tests cover: happy path, partial-fallback, total-failure, skip-due-to-lookback, and heterogeneous errors across providers.

---

## 3. Add `CascadeFailureReport` entity and persistence (D12 §6)

### What changes

New table storing the failure reports produced at the end of each daily job. Includes cleanup after the retention period.

### Where in code

- **`backend/app/market_data/models.py`**: new SQLAlchemy model `CascadeFailureReport` per D12 §6.1 schema, plus a helper model `CascadeFailureEntry` for the per-asset detail rows.
- **New Alembic migration:** creates the two tables and their indexes (on `run_completed_at` and on `failures.asset_id`).
- **`backend/app/tasks/daily_job.py`**: after the cascade completes, always persist a `CascadeFailureReport` row (even if `failures` is empty — enables aggregated reporting per §6.3).
- **New Celery periodic task** `cleanup_old_cascade_reports`: runs once per day, deletes reports older than `market_data.failure_report_retention_days`.

### Why

Per D12 §6, failure reports are the artifact that the header notification system and the administrator failure view consume. Without persistence, these features have nothing to display.

### Acceptance criteria

- After a daily job with mixed successes and failures, exactly one `CascadeFailureReport` row exists with the expected `resolved_by_provider` breakdown and one entry per failed asset in `failures`.
- Reports older than the retention window are removed by the cleanup task, and it does not remove more recent ones.
- The delete cascade from `CascadeFailureReport → CascadeFailureEntry` is atomic.

---

## 4. Deliver failure reports as header notifications (D12 §6.2)

### What changes

Extend the header notification system (D07 §10 / D10 §8) to include cascade failures. When a daily job completes, every user who owns at least one failed asset receives a new notification of type `cascade_failure`.

### Where in code

- **`backend/app/notifications/service.py`**: after the daily job completes, iterate over the failures grouped by user (each affected user gets one summary notification with the count of their failed assets) and enqueue notifications via the existing D07 notification mechanism.
- **`backend/app/api/notifications.py`**: extend the notification serializer to include the new type `cascade_failure` with a payload containing the affected assets (limited to the current user's own assets).
- **Frontend** (`frontend/src/state/notification-state.ts`, `frontend/src/components/header-bar.ts`): handle the new notification type. On click, open a modal (`pi-cascade-failure-modal`) listing the failed assets with their reason.

### Why

Per D12 §6.2, the failure report must reach the user without requiring them to navigate to a specific admin page. The header notification system already exists for AI job completions; adding a second notification type is the natural extension point.

### Acceptance criteria

- A user with 2 failed assets sees one notification saying "2 of your assets could not be updated today."
- Clicking opens a modal listing exactly those 2 assets with their reason (`not_found`, `rate_limited`, `insufficient_lookback`, or `provider_error`).
- The user does not see other users' failed assets.
- Notifications for successful runs are not created (only failures produce user-facing notifications).

---

## 5. Add the "Data providers" section to Settings (D12 §7)

### What changes

New section within the Settings screen, visible only to administrators, containing:

- Two reorderable lists: Market data providers and FX data providers.
- Per-provider display of API key status (masked or "Not configured") with the help text pointing to `.env`.
- A "Reset to defaults" button.
- A link to the cascade failure report history (§7 below).

### Where in code

- **Backend:**
  - **`backend/app/api/settings.py`** (existing router): add new endpoints `GET /settings/data-providers`, `PUT /settings/data-providers`, `POST /settings/data-providers/reset`. All guarded by `Depends(require_permission("system.view_config"))` per D11 §5.1.
  - Persistence of the ordered lists: since `config.yaml` is not writable at runtime by the app (per Spec 00f §5), the settings are stored in a small new table `system_settings` (key-value, per-user null since these are global) that overlays the `config.yaml` defaults. If the DB has an override, it wins; otherwise the config file value is used. This preserves the "no runtime mutation of config.yaml" rule while allowing the admin UI to change values.
  - **New Alembic migration:** creates the `system_settings` key-value table.
  - **`backend/app/config/loader.py`**: on read, merge DB overrides on top of `config.yaml` for keys under `market_data.providers` and `fx_data.providers` only. Other keys remain file-only. Document this narrow exception in a comment referencing D12 §7.
- **Frontend:**
  - **`frontend/src/screens/settings-screen.ts`**: add the "Data providers" section, conditionally rendered based on `hasPermission("system.view_config")`.
  - **New component:** `frontend/src/components/data-providers-editor.ts` implementing drag-and-drop reorder using the native HTML5 Drag and Drop API (no new dependencies).
  - **`frontend/src/api/settings.ts`**: functions for the three new endpoints.

### Why

Per D12 §7, the administrator needs to reorder or remove providers from the cascade without editing `config.yaml` and restarting. The read-only API-key view surfaces configuration status transparently while keeping secrets in environment variables (Spec 00b).

### Acceptance criteria

- An administrator sees the "Data providers" section in Settings; a regular investor does not (the section does not render at all).
- Drag-and-drop reordering persists to the DB and is reflected on the next daily job run.
- Removing all providers from the market data list shows a confirmation dialog and, if confirmed, results in the daily job skipping market data updates until the admin adds a provider back.
- The API key field for each provider shows a masked value or "Not configured", never the plaintext value.
- "Reset to defaults" restores the shipped order: `[twelve_data, eodhd, finnhub]` for market data, `[frankfurter]` for FX.
- All settings changes are audited in the request log (Spec 00b transparency).

---

## 6. Add the "Cascade failure report" admin view (D12 §7.4)

### What changes

A read-only view accessible from the Data providers section, showing the last 30 days of failure reports across all users. Filterable by date, provider, and reason.

### Where in code

- **Backend:**
  - **`backend/app/api/admin.py`**: add endpoint `GET /admin/cascade-failure-reports` guarded by `Depends(require_permission("system.view_audit_log"))`.
  - Query supports pagination (`page`, `page_size`) and filters (`from_date`, `to_date`, `provider`, `reason`).
- **Frontend:**
  - **New screen:** `frontend/src/screens/admin-cascade-failures-screen.ts`, route `/admin/cascade-failures`.
  - Link from the Data providers section.

### Why

Per D12 §7.4, the administrator benefits from an aggregated view to spot patterns (e.g. "provider X has been failing repeatedly this week") that per-user notifications do not surface.

### Acceptance criteria

- The admin sees a table of failure reports for the retention window, most recent first.
- Filtering by provider narrows to entries where that provider participated in the cascade.
- The view is read-only (no edit or delete actions).

---

## 7. Deprecate the single-provider config key (D12 §9)

### What changes

Replace `market_data.provider` (singular) with `market_data.providers` (list) in the config schema. Keep a backward-compatibility shim: if the old key is present and the new one is not, load a single-element list and log a deprecation warning.

### Where in code

- **`backend/app/config/schema.py`** (Pydantic model for `config.yaml`): change `market_data.provider: str` to `market_data.providers: list[str]`. Add a Pydantic root validator that handles the migration from the old key.
- **`backend/config.yaml`** (example): change the default entry to the list form. Retain a commented-out example of the old form for reference.
- **`docs/deprecations.md`** (create if missing): record the deprecation with expected removal date/version.

### Why

Per D12 §9, the cascade requires a list, not a single value. The compatibility shim prevents breakage for anyone whose local `config.yaml` still has the old key.

### Acceptance criteria

- A `config.yaml` with only `market_data.provider: twelve_data` (old form) loads successfully and produces `market_data.providers = ["twelve_data"]` with a deprecation warning in the startup log.
- A `config.yaml` with both keys defined uses the new one and logs a warning noting that the old is ignored.
- A `config.yaml` with only the new key loads silently.

---

## 8. Add EODHD environment variable (D12 §10, Spec 00e)

### What changes

Add `MARKET_DATA_EODHD_API_KEY` to the `.env.example` file and to the table of environment variables in Spec 00e §6.

### Where in code

- **`.env.example`**: add the new variable with a placeholder.
- **Spec 00e**: update the environment-variable table by adding a row. **This is the same narrow exception as prior changesets** (Spec 00e is the registry of env vars, so its table is updated in lockstep with any change that introduces one).
- **`backend/app/config/loader.py`**: at startup, if `eodhd` appears in `market_data.providers` but `MARKET_DATA_EODHD_API_KEY` is unset, fail startup with a clear error message ("provider `eodhd` is configured in `market_data.providers` but its API key is missing; either set MARKET_DATA_EODHD_API_KEY in .env or remove `eodhd` from the cascade in Settings").

### Why

Per D12 §10, the fail-fast validation ensures the operator learns about the misconfiguration at startup rather than at the first daily job execution.

### Acceptance criteria

- With `eodhd` in the cascade and no key set, startup fails with the specified message.
- With `eodhd` removed from the cascade, startup succeeds even if the key is unset.
- `.env.example` includes the new variable with an obvious placeholder value.

---

## 9. Update Spec 00f's registry of config keys

### What changes

Add the new keys (`market_data.providers`, `fx_data.providers`, `market_data.failure_report_retention_days`, `market_data.eodhd.*`) to Spec 00f's catalog table.

### Where in code

- **Spec 00f**: update the configuration-keys table (same lockstep exception applied to Spec 00e).

### Why

Spec 00f is the single registry of all configuration keys. New keys must be listed there so anyone reading it has a complete picture.

### Acceptance criteria

- Spec 00f's table lists every new key with type, default, and description as per D12 §9.

---

## 10. Order of implementation

To minimize interim breakage:

1. **Step 1** — Add the EODHD adapter (§1). Additive; no runtime effect until §2 uses it.
2. **Step 2** — Add the cascade layer (§2). Behind a feature flag `USE_CASCADE=false` at first, so the daily job still uses the single-provider path until the flag flips.
3. **Step 3** — Deprecate the config key (§7). Backward-compatible: old configs keep working.
4. **Step 4** — Add environment variable (§8) and Spec 00e update.
5. **Step 5** — Add `CascadeFailureReport` persistence (§3).
6. **Step 6** — Add notifications delivery (§4).
7. **Step 7** — Enable the cascade by removing the feature flag: `USE_CASCADE=true` by default. This is the moment behavior changes for end users.
8. **Step 8** — Add the Settings UI section (§5).
9. **Step 9** — Add the failure report admin view (§6).
10. **Step 10** — Update Spec 00f table (§9).

After all ten are applied and verified end-to-end, this changeset is marked `Implemented`.

---

## 11. What this changeset does not change

- **Spec D09's adapter interface (`MarketDataProvider`, `FxDataProvider`)** — unchanged, D12 uses it as-is.
- **Spec D09's `AssetPriceHistory` model** — unchanged; only the allowed `provider` enum values grow to include `eodhd` (a data-only change, not a schema change).
- **Spec D09's immutability of persisted historical data** — unchanged.
- **Spec D11's permission model** — the existing `system.view_config` and `system.view_audit_log` permissions cover the new admin surfaces; no new permission is added.
- **Spec 00b's API key policy (env vars only)** — reaffirmed, not changed.

---

## 12. Out of scope of this changeset

- Any of the items listed in D12 §11 (persistent memory across runs, editable API keys, multi-provider search, per-asset override, price reconciliation, historical rewrite on reorder, N-day provider-failure escalation).
- Encrypted-at-rest storage of secrets — remains firmly in scope of a hypothetical future spec if the project ever needs it.

---

## 13. Implementation notes (added when marked Implemented)

This changeset was written against an idealized file layout that predates it; the actual codebase differs in several places. None of these are spec changes — they are where the *file paths and mechanism* diverged from what §1–§9 assumed, while the *behavior* described still holds.

**Path differences.** The codebase uses `backend/app/services/market_data/` (not `backend/app/market_data/`), `backend/tests/unit/` (not `backend/tests/market_data/`), and there is no `backend/app/tasks/daily_job.py` — the daily job is `MarketDataService.run_daily_update()`, triggered on-demand via `POST /market-data/daily-update`, not a Celery beat schedule. No new scheduling infrastructure was added; the cascade and its persistence hang off this existing on-demand entry point.

**Step 6 (notification delivery) was descoped.** The header notification system this step assumed to extend doesn't exist as a generic mechanism in this codebase — today's header notifications are a poll of AI-job status only (`GET /ai-reports/jobs`), not a persisted, extensible notification store. Building that generic infrastructure was judged out of proportion to this changeset. Instead: `CascadeFailureReport` persistence (§3) and the admin cross-user view (§6/§7.4, delivered as Step 9) shipped as specified; the per-user header notification/modal (§4) did not. Failures are currently only visible to administrators via Settings → Data providers → "View cascade failure report history," not surfaced to the affected asset's owner directly. This is the one piece of D12 §6.2 not delivered.

**The daily job's lookback window needed splitting for EODHD to ever actually fire.** D12 §5.3 already anticipated that EODHD (365-day cap) can't serve a full bootstrap fetch, but the existing daily job requested a flat 400 days for *every* asset, bootstrap or not — meaning EODHD would be skipped on every single run and could never rescue a new asset, discovered via a live test with a real European ticker (see below). Fixed by splitting the cascade's requests into a ~350-day bootstrap batch (assets with no stored history yet) and an incremental batch windowed to the gap since the stalest already-tracked asset's last stored date, merged into one report via a new `merge_cascade_results()` helper. This was a necessary correctness fix, not scope creep — without it, "EODHD as a fallback" would have been true only in the config, never in practice.

**Real-world discrepancy found during live testing: Twelve Data's free tier does not actually cover all of BME.** Testing against a real Telefónica (TEF) holding produced `"This symbol is available starting with the Pro or Venture plan"` directly from Twelve Data's API — contradicting D09 §3.1 and D12 §3's own stated assumption that Twelve Data's free tier includes European exchanges. This is exactly the kind of gap Changeset C03 documented for Finnhub; the same caveat now applies, in part, to Twelve Data. EODHD resolving TEF correctly (once the lookback-window fix above was in place) is the concrete proof that this changeset's premise — EODHD as a genuine European-coverage fallback, not just a paper one — holds.

**`system_settings` (Step 8) is a new architectural pattern, not previously used in this codebase**: a DB table overlaying two specific `config.yaml` keys at runtime, cached in-process and invalidated on write, rather than queried per-request — see `services/settings_overlay.py`'s module docstring for the reasoning (the market data service builds its provider adapters in a synchronous, DB-independent singleton; threading a session through that call path would have been a bigger change than this narrow exception warranted).

**Verification.** Every step from EODHD adapter through the admin failure-report view was verified against the real dev database and real provider APIs (not mocks) via Docker, `scripts/db.ps1`, and — for the two frontend pieces (Settings' Data providers section, the admin failure-report screen) — a real headless-browser session (disposable test accounts, created and deleted per session) exercising drag-and-drop reorder, save, reset, filtering, and the admin-only visibility gate in both directions. Final state: 166 backend tests passing, `tsc --noEmit` clean, `ruff check` clean on every new/modified file (pre-existing lint debt elsewhere in the codebase was left alone, not touched).

**Post-implementation fix: `get_current_price` needed cascading too.** Originally scoped out of the cascade (§5.5 only names search and the batch job; on-demand current-price lookups were treated as out of D12's stated scope). This left a real, user-visible gap: the daily job correctly maintained TEF's price *history* via EODHD, but the asset detail page's "current price" widget — a separate on-demand call — stayed hard-wired to the primary (first-in-list) provider only, so it kept failing for TEF even after the daily job had started succeeding. Found by inspecting live backend logs after a user report ("providers are active, why doesn't TEF update"). Fixed by adding `MarketDataCascade.get_current_price()`, a single-ticker ordered-fallback method distinct from `execute()`'s batch semantics (mirrors the FX cascade's existing per-call fallback pattern), and wiring `MarketDataService.get_current_price()` to use it when the cascade is enabled. Verified against the real API: `GET /market-data/assets/TEF/price` now returns 200 (Twelve Data 404s, EODHD resolves it), where it previously returned 503. 168 backend tests passing (was 166; +2 for the new fallback/exhaustion cases).
