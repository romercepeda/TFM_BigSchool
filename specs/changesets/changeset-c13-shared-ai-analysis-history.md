# Changeset C13 — Share AI Analysis History Across Users of the Same Asset

**Status:** Implemented
**Type:** Cross-spec changeset (requirement change, not a bug fix)
**Triggered by:** Project owner review of the "AI Analysis" screen's Report History section: two different users who each hold the same asset (e.g. Intel) in their own portfolio currently see two disjoint histories — an analysis uploaded by one user is invisible to the other, even though both are looking at the same underlying company.
**Affects implementations of:** Spec D07 (AI-Powered Financial Report Analysis) §9.1, §11; Spec D10 (frontend architecture).

---

## 0. How to read this document

Spec D07 §11 currently states, explicitly and deliberately: *"A user can only see and delete `AnalysisReport`s and `UploadedFile`s they themselves created"* and *"The PDF content is never shared between users in v1, even if two users analyze the same report."* This was not an oversight — it was the v1 design decision. This changeset **reverses that decision for the Historial view only**, per explicit project owner instruction: *"si yo proceso [un análisis] para Intel, y luego más adelante Carolina crea cuenta y agrega Intel, también se le debe mostrar."*

Code and spec were aligned before this changeset (confirmed by direct inspection: `AnalysisReport.holding_id` was the only scope key, and both the API and the frontend queried strictly by `holding_id`). This is a requirement change, not a bug fix — recorded as a changeset per the project's Spec Driven Development discipline (Spec 00a).

---

## 1. What actually changes, and what does not

**Changes:**
- The Historial list (`GET .../ai-reports`) now returns every `AnalysisReport` for the **asset**, aggregated across every holding of every user that currently holds it — not just the requesting user's own holding.
- Viewing a single report's full detail (`GET /ai-reports/{id}`) is now allowed for any user who holds the same asset somewhere in their own portfolios, not only the original uploader.
- Each report in the response now carries `is_own: bool`, so the frontend can tell "my analysis" from "someone else's" and show edit/delete controls only for the former.

**Does not change:**
- **Editing** (`PATCH /ai-reports/{id}`) and **deleting** (`DELETE /ai-reports/{id}`) remain restricted to the original uploader (via `UploadedFile.user_id`), exactly as today. Sharing visibility does not mean shared write access — Carolina can see my Intel analysis, but only I can edit its date or delete it.
- **The PDF itself is still never shared.** `UploadedFile` rows, and the raw file bytes they hold, are not exposed by this changeset — only the already-public-facing `AnalysisReport` summary/detail fields (executive summary, metrics, signal, provider) become cross-visible. §11's "PDF content is never shared" sentence in D07 remains true; only the sentence about `AnalysisReport` visibility is superseded by this changeset.
- **Upload authorization** — a user can still only upload against a holding in their own portfolio (D07 §5 step 1, unchanged).
- **`IndicatorSnapshot` scoping.** This was already asset-scoped, not holding-scoped (D07 §9.2: `subject_id = holding.asset_id`) — i.e. the numeric fundamentals derived from any user's analysis were *already* shared across every holder of that asset, silently, before this changeset. This changeset brings the human-readable Historial (summary, signal, metrics card, PDF provenance) in line with a scoping model the indicator layer already had. See §6 for a pre-existing interaction this surfaces.

---

## 2. Data model — `AnalysisReport.asset_id`

| Field | Type | Notes |
|---|---|---|
| `asset_id` | UUID, FK → `assets.id` | Denormalized from `holding.asset_id` at creation time. Not nullable after backfill. Indexed — it is now the primary lookup key for the Historial list. |

`holding_id` is **kept** on `AnalysisReport` (unchanged) — it still records which holding originated the report, which is what the ownership/edit/delete checks and the D03 cascade-on-holding-delete rule (D07 §12) continue to key off. `asset_id` is additive, not a replacement.

### Where in code

- `backend/app/db/models/ai_report.py` — new column on `AnalysisReport`.
- `backend/app/worker/tasks.py` — `AnalysisReport(...)` construction (around the existing `holding_id=job.holding_id` line) gains `asset_id=holding.asset_id`. `holding.asset_id` is already loaded at that point in `_run_analysis` (used a few lines earlier for `fetch_system_context`), so this is a zero-extra-query addition.
- Migration: add the column nullable, backfill `analysis_reports.asset_id` from `holdings.asset_id` via `holding_id`, then set `NOT NULL` — same two-phase pattern already used by Changeset C05's `report_date_source` backfill.

### Why denormalize instead of joining through `Holding` on every read

`IndicatorSnapshot` already denormalizes `subject_id = holding.asset_id` at write time for the same reason (D07 §9.2) — this changeset follows the same precedent instead of introducing a second pattern (join-through-holding at read time) for conceptually the same problem.

---

## 3. Backend — service layer

### `get_reports_for_asset` (replaces `get_reports_for_holding`)

```
get_reports_for_asset(db, asset_id, *, current_user_id) -> list[dict]
```

Joins `AnalysisReport` to `UploadedFile` (outer join — a report whose `UploadedFile` was independently removed must still be visible, just with `is_own = False`) and returns one dict per report shaped for `AnalysisReportSummary`, with `is_own = (uploader_id == current_user_id)`. Sorted the same way as before (`report_date` desc, nulls last, then `created_at` desc) — now across every holding of every user that shares the asset.

### `get_own_report` (renamed from `get_report`)

Unchanged logic (owner-only lookup via `UploadedFile.user_id`) — kept exactly as-is, now under a name that makes the write-path authorization intent explicit. Used by `PATCH` and `DELETE`.

### `get_viewable_report` (new)

```
get_viewable_report(db, report_id, user_id) -> AnalysisReport | None
```

Returns the report if `user_id` either uploaded it, **or** currently holds `report.asset_id` in one of their own portfolios (`holdings JOIN portfolios ON holdings.portfolio_id = portfolios.id WHERE holdings.asset_id = report.asset_id AND portfolios.user_id = :user_id`). Used by the single-report `GET` endpoint (list-item expansion, and the post-upload result panel).

### Where in code

`backend/app/services/ai_report_service.py`.

---

## 4. Backend — API endpoints

### `GET /portfolios/{pid}/holdings/{hid}/ai-reports` (list)

Still validates the requesting holding belongs to the current user (`_require_holding`, unchanged — this is what stops a user from probing an asset's history before they hold it themselves). Once validated, resolves `holding.asset_id` and calls `get_reports_for_asset`, not `get_reports_for_holding`.

### `GET /ai-reports/{report_id}` (single report)

Now calls `get_viewable_report` instead of `get_own_report`.

### `PATCH /ai-reports/{report_id}` and `DELETE /ai-reports/{report_id}`

Unchanged: still call `get_own_report`. A 404 is returned if the requester is not the uploader — indistinguishable from "does not exist," consistent with the existing pattern elsewhere in this API for cross-user access attempts.

### Where in code

`backend/app/api/ai_reports.py`.

---

## 5. Backend — response schemas

`AnalysisReportSummary` (`backend/app/api/d07_schemas.py`) gains:

| Field | Type | Notes |
|---|---|---|
| `asset_id` | UUID | Exposed for completeness; not currently consumed by the frontend. |
| `is_own` | bool | Drives whether the frontend shows edit/delete controls for this entry. |

`AnalysisReportDetail` is unchanged — the expanded metrics view has no owner-only controls in the current UI (§7), so `is_own` is not needed there. If a future iteration adds owner-only actions to the detail view, it can be added then.

---

## 6. Frontend — `pi-analysis-screen`

### What changes

- The inline date/name edit icons (✎) and the "Eliminar análisis" button are only rendered when `r.is_own === true`. A report from another user renders its date/name as plain, non-interactive text.
- A small muted label (`analysis.history.entry.shared_label`, e.g. *"Análisis de otro usuario"*) is shown on non-own entries so it is clear at a glance why the controls are missing — this is not a name or identity disclosure, just a generic marker.
- No change to the upload flow, job polling, or the expanded-metrics panel — those already operate on whatever report the user is currently looking at, own or shared.

### Where in code

`frontend/src/screens/analysis-screen.ts` (`_renderDateField`, `_renderNameField`, the `report-actions` block in `render()`), `frontend/src/api/types.ts` (`AiReportSummary` gains `asset_id: string` and `is_own: boolean`).

### Acceptance criteria

- User A uploads an analysis for INTC. User B, who independently holds INTC in their own portfolio, opens their own Analysis screen for INTC and sees User A's report in the Historial list.
- User B cannot see the edit icons or the delete button on User A's report.
- User B can still expand it to see the full metrics/summary detail.
- User A still has full edit/delete control over their own report, from either user's screen.
- A user who does **not** hold the asset at all still cannot reach its history (the holding-ownership check on the list endpoint, and the asset-holding check on the single-report endpoint, both continue to gate access).

---

## 7. Translations (Spec D08)

Add to `frontend/src/i18n/locales/es.json` and `en.json`:

| Key | Spanish | English |
|---|---|---|
| `analysis.history.entry.shared_label` | Análisis de otro usuario | Analysis by another user |

---

## 8. Order of implementation

1. `backend/app/db/models/ai_report.py` + migration (add `asset_id`, backfill, `NOT NULL`, index).
2. `backend/app/worker/tasks.py` — set `asset_id` when constructing `AnalysisReport`.
3. `backend/app/services/ai_report_service.py` — `get_reports_for_asset`, rename `get_report` → `get_own_report`, add `get_viewable_report`.
4. `backend/app/api/d07_schemas.py` — `asset_id` + `is_own` on `AnalysisReportSummary`.
5. `backend/app/api/ai_reports.py` — wire the three endpoints to the renamed/new service functions.
6. `frontend/src/api/types.ts`, `frontend/src/screens/analysis-screen.ts` — types + conditional controls + shared label.
7. i18n key in both bundles.
8. Apply migration to production DB as part of deploy (schema change — see redeploy runbook, Changeset C09 §4.4).

---

## 9. What this changeset does not change

- `IndicatorSnapshot` scoping and the date-collision rule in `update_report_metadata` (C05 §7.1) — both were already asset-scoped; unchanged by this work (see §6 note below on a pre-existing interaction).
- The upload endpoint's authorization (still per-holding, per-portfolio-ownership).
- The `UploadedFile` PDF storage and its own-user-only access.
- The cascade-on-holding-delete rule (D07 §12) — still deletes only the `AnalysisReport`s/`AnalysisJob`s/`UploadedFile`s originating from the deleted holding, not every shared report visible through it.

---

## 10. Known pre-existing interaction surfaced by this change (not introduced by it)

Because `IndicatorSnapshot` rows for `ai_analysis` were already keyed by `asset_id` (D07 §9.2, D05 §5's "same `as_of_date` updates rather than duplicates" rule), two different users analyzing the same asset with the same `report_date` were **already** silently overwriting each other's indicator snapshot values before this changeset — the Historial *view* was private, but the derived indicator *data* was not. Making the Historial view shared does not create this interaction; it makes it visible/explainable for the first time (a user can now see whose analysis is currently "winning" a given date). Resolving the underlying collision semantics (e.g. attributing snapshots per-uploader, or a merge/consensus policy) is out of scope for this changeset and is left for a future iteration if it proves to be a real problem in practice.

---

## 11. Rationale

The project owner's stated mental model is that an asset's fundamentals — PER, ROE, executive summary, signal — are properties of the *company*, not of any one user's portfolio. Two users holding the same stock are looking at the same real-world entity and should benefit from each other's research rather than duplicating it. This mirrors the market-data layer (D09) and the indicator catalog (D05), both already shared globally per asset; D07's `AnalysisReport` was the one remaining piece of asset-relevant data still siloed per user, an inconsistency this changeset removes.

Keeping edit/delete uploader-only (rather than opening them to any holder) avoids the much harder problem of shared write conflicts — two users disagreeing about a report's date, or one user deleting research another relies on. Read-sharing with write-ownership is the same split already used successfully elsewhere in the app's authorization model (e.g. RBAC's view vs. edit permissions), so this is a consistent extension rather than a new pattern.
