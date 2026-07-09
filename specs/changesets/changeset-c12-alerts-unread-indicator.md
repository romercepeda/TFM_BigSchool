# Changeset C12 — Unread Indicator + Mark-as-Read for Touched Price Levels

**Status:** Implemented
**Type:** Cross-spec changeset (feature gap fix)
**Triggered by:** After wiring the Alerts Panel to real backend data (fixing the dead `alerts-screen.ts` stub), the project owner reviewed the live screen and found two missing pieces: no visual cue on the portfolio dashboard that a *new* alert exists, and no way to acknowledge a touched level without deleting it outright.
**Affects implementations of:** Spec D06 (Price Levels, Alert Engine & Analysis History), Spec D10 (frontend architecture), Spec D08 (i18n).

---

## 0. How to read this document

This is a small, additive changeset on top of Spec D06. It does not change the alert-crossing rules (§5 of D06), the two-table history design (§2), or any existing endpoint's contract — it adds one nullable column, one new endpoint, and a `unread_count` field to the existing portfolio alerts response introduced when D06 §6 (Alerts Panel) was actually wired to the frontend.

---

## 1. Motivation

Spec D06 §5.1 already states that a `touched` level "remains visible and continues to be shown in the Alerts Panel... until the user deletes it." That's correct for *data retention*, but it says nothing about *notification state*: once the project owner has looked at an alert, there was no way to tell the UI "I've seen this one" short of deleting the level entirely (which also throws away the price level itself, not just the notification).

Concretely, two gaps were found once the Alerts Panel became real:

1. **No indicator on the portfolio dashboard.** The "Alertas" button looks identical whether there are 0 or 10 touched alerts waiting. The user has to open the screen to find out.
2. **No lightweight acknowledgment.** The only existing action on a touched level was "Descartar" (hard delete, calling the same `DELETE .../price-levels/{id}` used for any level). Acknowledging that you've seen an alert should not force you to also give up the price level itself.

## 2. Scope decisions locked with the project owner

- **Only `touched` levels participate in read/unread state.** `armed` levels shown in the "Cerca de cruzar" (near-crossing) section are a continuously recomputed proximity indicator, not a discrete event — there is nothing to "acknowledge" about a live percentage gap. The unread badge counts touched-and-unseen levels only.
- **Marking read is separate from deleting.** "Descartar" (delete) is untouched — it still hard-deletes the level per D06 §3.3. A new, non-destructive "Marcar como leída" action only stamps the acknowledgment; the level (and its history) is unaffected.
- **No new history entry for a read acknowledgment.** D06 §4's `PriceLevelHistoryEntry.event_type` enum (`created` / `edited` / `touched` / `removed`) models analytically meaningful events. Reading a notification is a UI-only concern with no bearing on the analysis record, so it does not produce a history row.
- **Badge is a simple unread count**, not a full notification-center pattern (no per-alert "unread since" timestamps surfaced in the UI, no cross-device sync beyond what the DB already gives for free).
- **Existing touched levels default to unread** after this migration (the new column is nullable with no backfill) — there is no way to know retroactively whether the project owner had already "seen" a level touched before this feature existed, and defaulting to unread is the safer choice (never silently hides a real alert).

---

## 3. Data model — `PriceLevel.alert_seen_at`

| Field | Type | Notes |
|---|---|---|
| `alert_seen_at` | timestamp (UTC), nullable | Null while the touched alert is unread. Set to the acknowledgment time when the user marks it read. Meaningless while `status = armed` (always null there — armed levels have nothing to acknowledge). |

### Where in code

- `backend/app/db/models/price_level.py` — new column on `PriceLevel`.
- `backend/migrations/versions/` — new Alembic migration (`add_alert_seen_at_to_price_levels`), generated via `scripts/db.ps1 generate` per the project's standing convention.

### Why nullable with no default state machine

Reusing a single nullable timestamp (like `touched_at`) rather than a separate boolean keeps the "when" available for free should a future iteration want to show "seen 2 hours ago" — at negligible extra cost over a plain boolean.

---

## 4. Backend — mark-as-read endpoint

### What changes

New endpoint, nested under the same holding-scoped router as the rest of D06's price-level CRUD:

```
POST /portfolios/{portfolio_id}/holdings/{holding_id}/price-levels/{level_id}/mark-read
```

- Permission: `price_level.edit` (same as the existing `PATCH` endpoint — acknowledging a level is a mutation of the level's own state, not a read-only view action).
- 404 if the portfolio, holding, or level is not found (same ownership checks as the rest of the router, via the existing `_require_holding` helper).
- 409 if the level's `status` is not `touched` — an armed level has no alert to acknowledge.
- On success: sets `alert_seen_at = now()`, commits, returns the updated `PriceLevelResponse`.

### Where in code

- `backend/app/services/price_level_service.py` — new `mark_alert_seen(db, level)` function, alongside the other single-level mutators (`edit_price_level`, `delete_price_level`).
- `backend/app/api/price_levels.py` — new route handler.
- `backend/app/api/d06_schemas.py` — `PriceLevelResponse` gains `alert_seen_at: datetime | None` (inherited automatically by `PortfolioAlertItem`, which subclasses it).

### Acceptance criteria

- Marking an `armed` level's alert as read returns 409.
- Marking a `touched` level's alert as read sets `alert_seen_at`, returns 200 with the updated level, and does **not** write a `PriceLevelHistoryEntry` row.
- Marking an already-read level as read again is idempotent (just refreshes the timestamp — no error).

---

## 5. Backend — `unread_count` on the portfolio alerts endpoint

### What changes

`GET /portfolios/{portfolio_id}/alerts` (added when the Alerts Panel was wired up) now also returns:

```json
{
  "touched": [...],
  "near_crossing": [...],
  "unread_count": 2
}
```

`unread_count` is the number of items in `touched` where `alert_seen_at` is null. This is the single field the dashboard needs to decide whether to render a badge — no separate endpoint, no client-side recomputation logic duplicated across screens.

### Where in code

- `backend/app/api/d06_schemas.py` — `PortfolioAlertsResponse.unread_count: int`.
- `backend/app/services/price_level_service.py` — `list_portfolio_alerts` computes it alongside the existing `touched`/`near_crossing` split.

### Acceptance criteria

- A portfolio with 3 touched levels, 1 already marked read → `unread_count == 2`.
- A portfolio with 0 touched levels → `unread_count == 0`, regardless of how many near-crossing levels exist.

---

## 6. Frontend — dashboard badge

### What changes

`pi-dashboard-screen` fetches the portfolio's alerts (already-existing `getPortfolioAlerts`) alongside the portfolio and holdings it already loads, and renders a small numeric badge on the "Alertas" button **only when `unread_count > 0`**. The badge disappears entirely at 0 — no empty badge, no "0".

### Where in code

- `frontend/src/screens/dashboard-screen.ts` — `_load()` adds a third parallel fetch; `render()` conditionally renders the badge.
- `frontend/src/api/types.ts` — `PortfolioAlerts.unread_count: number`.

### Acceptance criteria

- Dashboard with 0 unread touched alerts: "Alertas" button has no badge.
- Dashboard with N > 0 unread touched alerts: badge shows N.
- Marking every touched alert as read (from the Alerts screen) and returning to the dashboard makes the badge disappear.

---

## 7. Frontend — mark-as-read action on the Alerts screen

### What changes

In the "touched" section of `pi-alerts-screen`, each unread alert (i.e. `alert_seen_at === null`) shows:

- A small unread marker (a dot) next to the alert.
- A **"Marcar como leída"** button, separate from the existing **"Descartar"** (delete) button.

Clicking "Marcar como leída" calls the new endpoint and reloads the list; the alert stays visible (it is not deleted) but loses its unread marker and the button is replaced by a muted **"Leída"** label. Already-read alerts never show the button again unless the underlying level transitions back through `armed → touched` (which per D06 §5.1 requires deleting and recreating the level, producing a fresh `alert_seen_at = null`).

### Where in code

- `frontend/src/api/price-levels.ts` — new `markAlertSeen(portfolioId, holdingId, levelId)`.
- `frontend/src/screens/alerts-screen.ts` — render + click handler for the new button; unread dot styling.

### Acceptance criteria

- An unread touched alert shows the dot and the "Marcar como leída" button.
- Clicking it removes the dot, shows "Leída" instead of the button, and the level is still present in the list (not deleted).
- "Descartar" still hard-deletes the level exactly as before this changeset.

---

## 8. Translations (Spec D08)

Add to `frontend/src/i18n/locales/es.json` and `en.json`:

| Key | Spanish | English |
|---|---|---|
| `alerts.mark_read` | Marcar como leída | Mark as read |
| `alerts.read` | Leída | Read |

---

## 9. Order of implementation

1. `backend/app/db/models/price_level.py` + migration (`scripts/db.ps1 generate "add alert_seen_at to price_levels"`, then `upgrade`).
2. `backend/app/services/price_level_service.py` — `mark_alert_seen`, and `unread_count` in `list_portfolio_alerts`.
3. `backend/app/api/d06_schemas.py` — schema fields.
4. `backend/app/api/price_levels.py` — new route.
5. `frontend/src/api/types.ts`, `frontend/src/api/price-levels.ts` — types + client call.
6. `frontend/src/screens/dashboard-screen.ts` — badge.
7. `frontend/src/screens/alerts-screen.ts` — unread marker + mark-read button.
8. i18n keys in both locale bundles.

---

## 10. What this changeset does not change

- The alert-crossing engine itself (D06 §5) — unchanged.
- `near_crossing` items — no read/unread state, never contribute to `unread_count`.
- "Descartar" (delete) — unchanged behavior and endpoint.
- `PriceLevelHistoryEntry` — no new event type; marking read is not a history event.

## 11. Out of scope of this changeset

- Push/email notifications — still explicitly out of scope per D06 §13.
- Per-alert "seen X minutes ago" display — the timestamp is stored but not surfaced in the UI yet.
- Bulk "mark all as read" action — each alert is acknowledged individually in v1.
- Any change to how `near_crossing` proximity alerts are computed or displayed.
