# Changeset C17 — Date-Based Alerts, In-Asset Alerts View, and App Version Display

**Status:** Implemented
**Type:** Cross-spec changeset (feature extension)
**Triggered by:** Project owner request: the "Alertas" feature currently only tracks price targets (Spec D06). He wants to keep that unchanged, but also be able to attach a date + short description to any asset — starting with "next earnings report" dates, but generic enough for anything he wants to be reminded to check. He also wants alerts visible from inside the asset detail screen (not only the portfolio-wide Alerts Panel), and a small app version indicator in the header that a future session bumps automatically on every published changeset / new spec, without being told again each time.
**Affects implementations of:** Spec D06 (Price Levels, Alert Engine & Analysis History) — extended, not modified; Spec D10 (frontend architecture); Spec D11 (Roles & Permissions) — new permission codes; Spec 00f (Global Configuration) — new config key.

---

## 0. How to read this document

Three additive pieces bundled together because they were requested together and the first two share the same screens:

1. **§1–§6** — the new `DateAlert` entity: a lightweight, per-holding "remind me on this date" alert, modeled after `PriceLevel` but deliberately simpler (no immutable history, no crossing engine — see §2 for why).
2. **§7** — a new "Alertas" section embedded directly in the Asset Detail screen, showing this holding's active alerts (both kinds) without navigating away.
3. **§8** — the app version indicator and the standing versioning rule.

Nothing about the existing price-level flow changes. `PriceLevel`, its history table, the crossing engine, and the existing Alerts Panel and Set-Levels screens keep working exactly as they do today.

---

## 1. Scope decisions locked for this changeset

- **`DateAlert` is a new, independent entity — not a generalization of `PriceLevel`.** They're both "alerts" at the UI level, but structurally different enough (a price crossing vs. a calendar date) that forcing one table with nullable columns for both would make every query messier for no real gain. This mirrors the same reasoning Spec D06 §14 used to justify splitting `PriceLevel` from `PriceLevelHistoryEntry`: different lifecycles, kept apart.
- **No immutable history table for `DateAlert` (v1).** Spec D06's history table exists to satisfy one specific, explicitly stated requirement: *"que una vez yo haya analizado una acción... eso en el tiempo no se me olvide"* — the analytical record of a price thesis must never be lost. A date reminder ("Informe Q4 el 12/02") carries no such analytical weight; editing or deleting it loses nothing worth preserving. If this turns out wrong in practice, a history table can be added later without restructuring `DateAlert` itself (same escape hatch Spec D06 §14 relied on).
- **No crossing "engine" or daily job.** A price level needs the daily price-update job (Spec D09) to know when a target was crossed. A date alert's status is a pure function of `alert_date` vs. today's date — computed on every read, not materialized by a background job. This is simpler and cannot go stale.
- **Editing is unrestricted, unlike a touched `PriceLevel` (D06 §3.2).** A touched price level locks its price/direction because changing it would falsify the historical record. A date alert has no such record to protect, so its date and description stay editable in every status — e.g. the user can push a report date back after an "already due" alert if the company delayed its publication, without deleting and recreating.
- **Reuses the exact read/unread pattern from Changeset C12** (`alert_seen_at`, mark-as-read, unread badge) rather than inventing a new one — the project owner is already used to this interaction from price levels, and combining both alert kinds into a single `unread_count` on the dashboard badge means one number tells him "there's something to look at," regardless of type.
- **The embedded Asset Detail alerts view (§7) shows only "needs attention now" items** — touched price levels and due date alerts. It deliberately does **not** duplicate the "near crossing" / "upcoming" pre-alert lists from the portfolio-wide Alerts Panel — those remain exclusive to that screen, which is the dedicated early-warning surface. Duplicating that proximity logic into the asset screen would mean two places computing "is this close" with the risk of drifting apart.

---

## 2. `DateAlert` entity

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `holding_id` | UUID | FK → `holdings.id`, `ON DELETE CASCADE`. Same scoping as `PriceLevel` — an alert belongs to a specific holding in a specific portfolio. |
| `alert_date` | Date | The date being watched for (e.g. an expected earnings report date). No constraint against being in the past at creation time — the user may want to log something retroactively or just made a typo they'll fix. |
| `description` | Text, **not null** | Short free-text reason for the alert (e.g. "Publicación de resultados Q4"). Required — unlike `PriceLevel.note`, which is optional, a date alert with no description is meaningless. |
| `alert_seen_at` | timestamp (UTC), nullable | Null = unread. Same semantics as `PriceLevel.alert_seen_at` (Changeset C12). Only meaningful once the alert is `due` (§3). |
| `created_at` / `updated_at` | timestamp (UTC) | Standard audit timestamps. |

No `status` column — status is derived at read time (§3), never stored, so it can't go stale.

### Where in code

- `backend/app/db/models/date_alert.py` — new ORM model.
- `backend/app/db/models/holding.py` — new `date_alerts` relationship (`cascade="all, delete-orphan"`, mirroring `price_levels`).
- `backend/app/db/models/__init__.py` — register for Alembic autodiscovery.
- New Alembic migration via `scripts/db.ps1 generate "add date_alerts table"`.

---

## 3. Status (derived, not stored)

A `DateAlert` is in exactly one of two states, computed from `alert_date` vs. "today" (`datetime.now(UTC).date()` — same UTC-date convention used elsewhere in the backend, no market-calendar dependency since this isn't tied to trading days):

- **`pending`** — `alert_date > today`. Nothing to see yet.
- **`due`** — `alert_date <= today`. The date has arrived or passed; this is the "alert" state, analogous to a `touched` price level.

There is no automatic transition to "acknowledge and archive" — a due alert stays visible (and included in `unread_count` while unread) until the user marks it read or deletes it, same as a touched price level.

---

## 4. Backend — service & endpoints

New service module `backend/app/services/date_alert_service.py`, mirroring `price_level_service.py`'s shape minus the history/crossing pieces:

- `list_date_alerts(db, holding_id)` — all alerts for a holding, ordered by `alert_date` ascending.
- `create_date_alert(db, holding_id, alert_date, description)` — single-item create (unlike `PriceLevel`'s batch endpoint — a date alert is naturally a one-off, there's no "laddering" use case to batch).
- `edit_date_alert(db, alert, alert_date=None, description=None)` — always allowed, no touched-style lock (§1).
- `mark_alert_seen(db, alert)` — sets `alert_seen_at = now()`. Raises `ValueError` if the alert is still `pending` (nothing to acknowledge yet — same 409 pattern as `price_level_service.mark_alert_seen`).
- `delete_date_alert(db, alert)` — hard delete, no history write (§1).
- `list_portfolio_date_alerts(db, portfolio_id, *, upcoming_days)` — aggregation for the portfolio Alerts Panel (§6), returns `(due, upcoming, unread_count)`:
  - `due`: `alert_date <= today`, sorted by `alert_date` descending (most recently due first — same "recency first" convention as touched price levels).
  - `upcoming`: `today < alert_date <= today + upcoming_days`, sorted by `alert_date` ascending (soonest first — same convention as near-crossing's "smallest gap first").
  - `unread_count`: count of `due` items with `alert_seen_at is null`.

No holding-cascade cleanup code is needed anywhere (unlike `PriceLevel`'s orphan-preserving history table, Spec D06 §11) — `date_alerts.holding_id` has a normal `ON DELETE CASCADE` FK, so deleting a holding or a portfolio removes its date alerts automatically through the existing cascade chain.

### Endpoints

New router `backend/app/api/date_alerts.py`, nested identically to price levels:

```
GET    /portfolios/{portfolio_id}/holdings/{holding_id}/date-alerts             — list
POST   /portfolios/{portfolio_id}/holdings/{holding_id}/date-alerts             — create one
PATCH  /portfolios/{portfolio_id}/holdings/{holding_id}/date-alerts/{alert_id}  — edit
DELETE /portfolios/{portfolio_id}/holdings/{holding_id}/date-alerts/{alert_id}  — hard delete
POST   /portfolios/{portfolio_id}/holdings/{holding_id}/date-alerts/{alert_id}/mark-read
```

Registered in `backend/app/main.py` alongside the price-levels router.

### Schemas

`backend/app/api/date_alert_schemas.py` — `DateAlertIn`, `DateAlertPatch`, `DateAlertResponse` (includes a computed `status: Literal["pending","due"]` field set in the endpoint, not stored), `PortfolioDateAlertItem` (adds `asset_ticker`/`asset_name`).

---

## 5. Permissions (Spec D11)

New permission codes, following the exact `price_level.*` pattern, added to `backend/roles_catalog.yaml` and granted to both existing roles (`administrator`, `investor` — same set that already holds every `price_level.*` permission):

- `date_alert.view`
- `date_alert.create`
- `date_alert.edit` (also gates mark-read, same convention as `price_level.edit`)
- `date_alert.delete`

---

## 6. Configuration (Spec 00f)

New key under the existing `alerts` section:

| Key | Type | Default | Description |
|---|---|---|---|
| `alerts.date_upcoming_days` | int | `14` | A date alert is shown in the Alerts Panel's "upcoming" pre-alert list when it falls within this many days from today. Mirrors `alerts.near_crossing_pct`'s role for price levels. |

`backend/app/config.py` (`AlertsConfig`) and `backend/config.yaml` both updated.

---

## 7. Portfolio Alerts Panel — merged view (Spec D06 §6, extended)

`GET /portfolios/{portfolio_id}/alerts` now returns both alert kinds in one response:

```json
{
  "touched": [...],
  "near_crossing": [...],
  "date_due": [...],
  "date_upcoming": [...],
  "unread_count": 3
}
```

`unread_count` becomes the **sum** of unread touched price levels and unread due date alerts — one number for the dashboard badge (Changeset C12 §6), so the project owner doesn't need to check two counts to know something needs attention.

### Where in code

- `backend/app/api/d06_schemas.py` — `PortfolioAlertsResponse` gains `date_due: list[PortfolioDateAlertItem]`, `date_upcoming: list[PortfolioDateAlertItem]`.
- `backend/app/api/portfolios.py` — `get_alerts` calls both `price_level_service.list_portfolio_alerts` and `date_alert_service.list_portfolio_date_alerts`, sums the two `unread_count`s.

### Frontend — Alerts screen

`frontend/src/screens/alerts-screen.ts` gains a "Fechas" section (due dates, styled like the existing touched-price-level cards — unread dot, mark-as-read, dismiss) and reuses the existing "upcoming" rendering pattern for `date_upcoming` under a shared "próximamente" heading. Empty state only shows when all four lists are empty.

---

## 8. In-asset alerts view (new requirement, not previously supported even for price levels)

Today, the Asset Detail screen only links out to a separate "Niveles de precio" screen — a touched price level isn't visible without navigating away. The project owner explicitly asked to see alerts *"como ya las vemos hoy en día, pero también desde dentro del activo."*

### What changes

`asset-detail-screen.ts` fetches this holding's price levels and date alerts (two more parallel requests alongside indicators/price) and renders a new "Alertas" section — shown only when there's at least one touched price level or due date alert for this holding — with the same mark-as-read / dismiss actions as the portfolio Alerts screen, scoped to just this asset. Per §1, this section intentionally excludes near-crossing/upcoming pre-alerts (that stays exclusive to the portfolio-wide panel).

The existing "Niveles de precio" button/screen is relabeled **"Alertas"** (button `screen.holding.alerts`) and now shows both the existing price-level form/list (unchanged) and a new "Alertas de fecha" sub-section (new form/list) — one screen for defining every alert on this asset, consistent with the project owner framing this as one feature ("modificar la funcionalidad de Alertas... agregarle"), not two parallel ones. The route itself is unchanged (`.../assets/:holdingId/levels`) — this is a content-only change to an existing screen, not a new page.

### Where in code

- `frontend/src/screens/set-levels-screen.ts` — add the date-alerts form + list section; page heading changes from "Niveles de precio" to "Alertas" (new i18n key), the existing price-levels sub-heading keeps its current text.
- `frontend/src/components/date-alert-form.ts` — new component, modeled on `price-level-form.ts` (date input + description input).
- `frontend/src/api/date-alerts.ts` — new API client module, modeled on `price-levels.ts`.
- `frontend/src/api/types.ts` — `DateAlert`, `DateAlertStatus`, `PortfolioDateAlertItem`, extended `PortfolioAlerts`.
- `frontend/src/screens/asset-detail-screen.ts` — new "Alertas" section + two more parallel fetches in `_load()`; button label change (`screen.holding.price_levels` → `screen.holding.alerts`).

---

## 9. Translations (Spec D08)

New keys added to `frontend/src/i18n/locales/es.json` and `en.json` (exact list finalized during implementation, following the existing `screen.price_level.*` / `alerts.*` naming), covering: the "Alertas" button/page title, the date-alert form fields (date, description), status labels (`pending`/`due`), and the new Alerts Panel sections ("Fechas" / "Próximamente").

---

## 10. App version indicator

### What changes

A small version subscript appears next to the "Portfolio IA" brand text in the global header (`header-bar.ts`), e.g. **Portfolio IA `v1.0.0.0`**. Purely cosmetic — no functional impact.

### Versioning scheme (4 segments: `MAJOR.MINOR.SPEC.CHANGESET`)

- The last segment increments by 1 every time a changeset is committed and published (pushed) — e.g. `1.0.0.1` → `1.0.0.2`.
- The third segment increments by 1, and the last segment resets to `0`, every time a new spec is added under `specs/domain/` or `specs/00-engineering/` — e.g. `1.0.0.1` → `1.0.1.0`.
- The first two segments (`MAJOR.MINOR`) are untouched by this automatic rule — bumped only on an explicit request for a major/minor release.

This rule is recorded as a standing project memory (not just in this document) so any future session applies it automatically, without the project owner having to repeat the instruction. See the memory file `feedback-app-versioning.md`.

### Where in code

- `frontend/src/version.ts` — new file, single source of truth: `export const APP_VERSION`.
- `frontend/src/components/header-bar.ts` — renders `APP_VERSION` as a small `<span class="version-tag">` next to the brand name.

`APP_VERSION` was kept at the `1.0.0.0` baseline while this changeset was reviewed locally, and bumped to `1.0.0.1` in the same commit that published it, per the versioning rule above.

---

## 11. Order of implementation

1. `backend/app/db/models/date_alert.py`, `holding.py` relationship, `__init__.py` registration.
2. `scripts/db.ps1 generate "add date_alerts table"`, review migration, `scripts/db.ps1 upgrade`.
3. `backend/app/api/date_alert_schemas.py`.
4. `backend/app/services/date_alert_service.py`.
5. `backend/app/api/date_alerts.py`; register in `main.py`.
6. `backend/roles_catalog.yaml` — new permission codes on both roles.
7. `backend/app/config.py`, `backend/config.yaml` — `alerts.date_upcoming_days`.
8. `backend/app/api/d06_schemas.py`, `backend/app/api/portfolios.py` — merge into `/alerts`.
9. `frontend/src/api/types.ts`, `frontend/src/api/date-alerts.ts`.
10. `frontend/src/components/date-alert-form.ts`.
11. `frontend/src/screens/set-levels-screen.ts` — add date-alerts section, relabel heading.
12. `frontend/src/screens/asset-detail-screen.ts` — embedded Alertas section, button relabel.
13. `frontend/src/screens/alerts-screen.ts` — Fechas section.
14. `frontend/src/version.ts`, `frontend/src/components/header-bar.ts`.
15. i18n keys in both locale bundles.
16. Local verification (backend boots, migration applies cleanly, `npm run build`/i18n validation passes, manual click-through) — reviewed locally by the project owner first, per his explicit instruction, before being committed/pushed/deployed.

## 12. What this changeset does not change

- `PriceLevel`, `PriceLevelHistoryEntry`, the crossing engine, or any existing price-level endpoint — all untouched.
- The existing Alerts Panel's touched/near-crossing sections and sort order.
- Any AI analysis, indicator, or FX/market-data logic.

## 13. Out of scope of this changeset

- Push/email/other out-of-app notifications for date alerts — same v1 boundary as D06 §13.
- Recurring date alerts (e.g. "every quarter") — v1 is single one-off dates only; the user recreates it next quarter.
- A history/audit trail for date alerts (§1) — can be added later without restructuring the entity.
- Any change to the MAJOR/MINOR version segments — those remain a manual, explicit decision.
