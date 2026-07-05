# Changeset C05 — Editable Report Date and Name on AI Analyses

**Status:** Pending implementation
**Type:** Cross-spec changeset
**Triggered by:** UX gap discovered during v1 usage — the analysis history uses the upload date rather than the actual financial report date, and there is no human-readable name to identify what report a data point came from.
**Affects implementations of:** Spec D07, Spec D05, Spec D10, Spec D08

---

## 0. How to read this document

This changeset applies **two related changes** to the code that implements the AI analysis pipeline of Spec D07 and the indicator snapshot rendering of Spec D05. As always: **do not rewrite the original specs**. This document is the source of truth for what changes in the code and why.

---

## 1. Motivation

Two operational gaps discovered while using the system:

1. **`IndicatorSnapshot.as_of_date` is set to the upload date, not the actual report date.** When a user uploads a Q1 2026 financial report in July 2026, the indicator's historical value is recorded as *"July 2026"*, which misrepresents the timeline of the underlying financial data. The report itself typically references a specific accounting period (Q1 2026, FY 2025, H1 2026, etc.) and that is the date the value should be associated with.

2. **No human-readable identifier for the source report.** When the indicator card shows two historical values, they appear as bare numbers next to bare dates (`2 jul: 59.857`, `1 jul: 59.342`). The user has no way to know at a glance which report each value came from — was it the Q1 quarterly report? The annual report? A press release? A tooltip showing the report name (`"Q1 2026"`, `"FY 2025"`) would close that gap.

Both problems are fixable together because the AI already reads the PDF and can extract both pieces of information (the report's fiscal period date and its short name/label) as part of the same extraction call.

---

## 2. Scope decisions locked with the project owner

- The AI extracts a **suggested date** and a **suggested name** during PDF processing. These are stored **as-is** on the `AnalysisReport` and used immediately to date and label the derived `IndicatorSnapshot`s. **No blocking confirmation dialog**: the user can edit both fields afterward from the analysis history.
- If the AI could not deduce the date, the system falls back to the **upload date** and displays a visible warning in the analysis history entry (see §6).
- The name is **mandatory**. If the AI could not deduce a name, the field is empty on save; the user must fill it in before the tooltip in indicator cards will render meaningfully. Empty names surface a persistent warning in the analysis history.
- Editing the date or name in the history **updates the associated `IndicatorSnapshot`s** so that indicator cards and tooltips reflect the new values on the next render.

---

## 3. Extend the AI extraction schema (Spec D07 §4.2)

### What changes

Add two new fields to the AI extraction JSON schema (currently `report_date`, `metrics`, `executive_summary`, `global_signal`, `confidence_notes`):

- **`report_period_name`** (string, nullable) — a short label identifying the accounting period the report covers. Examples: `"Q1 2026"`, `"FY 2025"`, `"H1 2026"`, `"9M 2025"`. The AI is instructed to prefer the compact conventional form used in the report itself.
- **`report_date`** already exists in the schema and its semantics **do not change**: it remains "the date the report identifies as its fiscal reference point." This is the date used as `as_of_date` for derived snapshots (see §5).

### Where in code

- **`backend/ai_extraction_schema.json`** — add the `report_period_name` field with type `string | null`.
- **`backend/ai_extraction_prompt.md`** — extend the prompt to instruct the model to also produce the `report_period_name`, with concrete examples of expected forms.
- **`backend/app/analysis/schemas.py`** — extend the Pydantic model that validates the AI response with the new field.
- **Unit tests** for the schema loader in `backend/tests/analysis/test_extraction_schema.py`: add cases for reports where the name is present, absent (null), and non-standard.

### Why

Per Spec D07 §4, the extraction schema is the contract between the prompt and the pipeline. Adding one nullable field is the minimally invasive change; no existing field is renamed or reshaped.

### Acceptance criteria

- The updated schema validates responses with and without `report_period_name`.
- The AI prompt file explicitly asks for the name in the same JSON structure as the metrics.
- Existing analyses in the database remain readable; missing `report_period_name` is treated as `null`.

---

## 4. Extend the `AnalysisReport` entity (Spec D07 §8.2)

### What changes

Add two new columns to the `analysis_reports` table:

- **`report_period_name`** (string, nullable) — the value extracted by the AI or entered manually by the user.
- **`report_date_source`** (enum: `ai_extracted` | `upload_fallback` | `user_edited`) — records whether the current `report_date` came from the AI, from the upload-date fallback (when the AI could not deduce it), or from a manual user edit. Used to render the "AI could not deduce date" warning in the UI.

The existing column `report_date` remains **nullable in the DB but always populated** after §5 runs — the fallback ensures no analysis is left with a null date.

Add a matching column for the name source: **`report_period_name_source`** (enum: `ai_extracted` | `user_edited` | `unset`). `unset` means neither the AI nor the user has provided a name yet, which is what surfaces the persistent "please add a name" warning in the history.

### Where in code

- **`backend/app/analysis/models.py`** — add the four columns (two data columns + two source enums).
- **New Alembic migration**: add columns. Backfill for existing rows:
  - `report_period_name = NULL`, `report_period_name_source = 'unset'`.
  - `report_date_source = 'upload_fallback'` for any existing row whose current `report_date` matches its `created_at` date (best-effort inference).
  - Rows where `report_date` was previously set from the AI keep their date and get `report_date_source = 'ai_extracted'`. Since this cannot be reliably distinguished on legacy rows, mark all pre-migration rows as `report_date_source = 'legacy_unknown'` (adding this fourth enum value only for the backfill). Newer rows will use the three semantic values only.

### Why

Per §2, the system must distinguish AI-extracted values from user-edited ones so the UI can show appropriate warnings and so audit is possible. Without the source enum, editing history would lose the origin information.

### Acceptance criteria

- New analyses persist with `report_date_source = 'ai_extracted'` (or `'upload_fallback'` when the AI returns null for the date) and `report_period_name_source` set accordingly.
- User edits from the history UI (see §7) change the values and update the source enums to `user_edited`.
- The migration does not require downtime and handles nullability correctly.

---

## 5. Use the report's date and name in derived snapshots (Spec D05 §5, Spec D07 §9.2)

### What changes

When the analysis worker persists an `AnalysisReport` and generates its derived `IndicatorSnapshot`s:

1. If `report_date` was extracted successfully → use it as `IndicatorSnapshot.as_of_date`.
2. If not → fall back to the upload date (`AnalysisJob.completed_at` truncated to date), set `report_date_source = 'upload_fallback'`, and use that date as `as_of_date`.
3. `report_period_name` is stored on the report only. **Snapshots do not carry the name directly.** The name is resolved at render time by joining `IndicatorSnapshot.source_ref → AnalysisReport.id → report_period_name` (see §8 for the render join).

### Where in code

- **`backend/app/analysis/service.py`** (worker function that creates the report and snapshots): implement the fallback logic and the source-enum assignment.
- **`backend/tests/analysis/test_worker.py`**: add tests covering (a) AI returns valid date → snapshot uses it; (b) AI returns null → fallback used; (c) AI returns a date that is in the future → treat as if AI returned null (safety check).

### Why

Per §2, the whole point of C05 is that the snapshot's `as_of_date` reflects the accounting period, not the upload event. Without this change, extending the schema and the entity would leave the snapshots still using upload dates.

### Acceptance criteria

- A test PDF where the AI extracts `report_date = "2026-03-31"` produces snapshots with `as_of_date = 2026-03-31`, regardless of when the user uploaded it.
- A PDF where the AI returns null date produces snapshots with `as_of_date = upload date` and the report entity has `report_date_source = 'upload_fallback'`.
- The unification rule of D05 §5 ("a re-analysis with the same `as_of_date` updates the snapshot rather than duplicating") continues to work correctly with the new date logic.

---

## 6. Warning banners in the analysis history entry (Spec D10 UI)

### What changes

In the analysis history list (Screen 9 per D10), each entry displays inline warnings when applicable:

- **If `report_date_source = 'upload_fallback'`** → show a small yellow icon with tooltip: *"La IA no pudo determinar la fecha del informe. Se usó la fecha de subida."*
- **If `report_period_name_source = 'unset'`** → show a persistent inline "warning" state: *"Añade un nombre para identificar este informe (ej. Q1 2026)."*
- **If both are edited by the user** → show no warning; the entry is treated as confirmed.

The warnings do not block use of the analysis; they just make the fallback state visible.

### Where in code

- **`frontend/src/screens/history-screen.ts`** — extend the rendering of each entry with the warning slots.
- **`frontend/src/i18n/locales/es.json` and `en.json`** — add new keys for the warning strings.

### Why

Per §2, the fallback flow must be transparent. The user needs to know when the system had to guess and be nudged to provide the missing information.

### Acceptance criteria

- A report with `upload_fallback` displays the yellow icon and tooltip.
- A report with `unset` name displays the "Añade un nombre" prompt.
- A user-edited report displays no warning.
- Both warnings are translated to Spanish and English per Spec D08.

---

## 7. Editable date and name in the history (Spec D10)

### What changes

In the analysis history entry, add two inline-editable fields for `report_date` and `report_period_name`. Editing behavior:

1. User clicks a small pencil icon on the entry, or the field itself becomes editable on focus.
2. User types the new value; the date field uses a native `<input type="date">`; the name field is a plain text input (max 40 characters).
3. On blur or Enter, the change is submitted via `PATCH /analyses/{id}` to the backend.
4. On success, the backend updates the report row, updates the source enums to `user_edited`, and **updates the `as_of_date` of all `IndicatorSnapshot`s whose `source_ref` matches this report**. If the new date collides with an existing snapshot at the same `(indicator, subject, date)`, per D05 §5 the existing one is updated with the new values (or, if the new date frees up the previous snapshot, the previous one is deleted — see §7.1 for the collision rule).
5. On error, the field reverts to its previous value and displays an inline error message.

### 7.1 Date-edit collision rule

Editing the date of an analysis can create a conflict with another existing snapshot for the same `(indicator, subject, as_of_date)` tuple. The rule applied:

- If **no collision** → the snapshots' `as_of_date` is updated in place.
- If **collision with another snapshot from a different analysis** → the edit is rejected with HTTP 409 and a UI message: *"Ya existe un análisis con esta fecha para este activo. Elige otra fecha o elimina el análisis existente primero."* This prevents silent overwriting of another analysis's data.
- If **collision with a snapshot from the same analysis** (e.g. the user is undoing a previous edit) → the snapshots' `as_of_date` is updated in place. This is the normal "consolidation" case.

### Where in code

- **Backend:**
  - **`backend/app/api/analyses.py`** — add `PATCH /analyses/{id}` guarded by `Depends(require_permission("analysis.edit"))` (new permission, see §9). Accepts `{report_date?: string, report_period_name?: string}`. Applies the collision rule.
  - **`backend/app/analysis/service.py`** — add `update_report_metadata(...)` that performs the atomic transaction: update report + snapshots.
- **Frontend:**
  - **`frontend/src/screens/history-screen.ts`** — the inline-editing UI, with clear visual states for "editable", "saving", "saved", "error".
  - **`frontend/src/api/analyses.py`** — add the `patchAnalysis(...)` client function.

### Why

Per §2 project owner decision, the user must be able to correct the AI's guesses or add missing information without re-uploading the PDF. Without this, the AI's occasional misreads become permanent.

### Acceptance criteria

- Editing the date of an analysis updates the entry immediately, and the change reflects in the indicator card historical values and their tooltip on next render.
- Editing the name of an analysis updates the tooltip shown in indicator cards for that report's derived values.
- A collision with another analysis returns HTTP 409 and the UI shows the specific message.
- The edit is atomic: either the report + all snapshots update together, or none does.

---

## 8. Show `report_period_name` as tooltip on indicator card historical values (Spec D05 UI)

### What changes

In the indicator card widget (used on Screen 6 — Asset Detail), each historical value shown ("2 jul: 59.857", "1 jul: 59.342") gains a hover tooltip that displays the `report_period_name` of the analysis that produced that value.

- If the value came from an AI analysis (`IndicatorSnapshot.source = 'ai_analysis'`) → tooltip shows the report's name (e.g. `"Q1 2026"`) or, if the name is `unset`, shows *"Sin nombre — edítalo en Historial de análisis"*.
- If the value came from the scheduled daily job (`source = 'scheduled_job'`) → no tooltip is shown (there is no "report" behind a market-data-derived value).

### Where in code

- **Backend:**
  - **`backend/app/indicators/service.py`** — extend the query that returns indicator historical values so it joins `IndicatorSnapshot.source_ref` → `AnalysisReport.report_period_name`. The response now includes an optional `source_report_name` field per historical value.
- **Frontend:**
  - **`frontend/src/components/indicator-card.ts`** — render a native `title=` attribute or a small tooltip overlay on each historical value when `source_report_name` is present. Use existing CSS variables per D10 §10.

### Why

Per §2 project owner decision, tooltips give the user a way to trace an indicator's historical value back to the report that produced it. Without them, historical values are anonymous numbers.

### Acceptance criteria

- Hovering a historical value of an AI-sourced snapshot displays the report name in a tooltip.
- Values from the scheduled daily job do not show a tooltip.
- Missing report names show the "Sin nombre" hint rather than an empty tooltip.
- The join adds negligible overhead to the indicator query (verified by query plan review).

---

## 9. Add `analysis.edit` permission (Spec D11)

### What changes

Introduce a new permission code **`analysis.edit`** that gates the new `PATCH /analyses/{id}` endpoint. Assign it to both the `investor` and `administrator` roles in the roles catalog.

### Where in code

- **`backend/roles_catalog.yaml`** — add `analysis.edit` under permissions; assign to both roles.
- **Spec D11 §5.1 catalog table** — update the analysis-domain row to include `analysis.edit` (same lockstep exception used for changes to specs whose tables are the single source of truth for their contents).

### Why

Per D11 §8, every endpoint declares a `require_permission`. The new PATCH endpoint needs its own permission code, distinct from `analysis.upload` and `analysis.delete`.

### Acceptance criteria

- The roles catalog seed at startup produces the new permission.
- Both roles have it in v1.
- An unauthenticated or unauthorized user calling PATCH receives HTTP 403.

---

## 10. Translations (Spec D08)

### What changes

Add all new i18n keys to `frontend/src/i18n/locales/es.json` and `en.json`:

- `analysis.history.entry.date_fallback_warning` — tooltip text on the yellow-icon warning.
- `analysis.history.entry.name_missing_warning` — persistent name-missing hint.
- `analysis.history.entry.edit_date_label` — label of the date field.
- `analysis.history.entry.edit_name_label` — label of the name field.
- `analysis.history.entry.date_collision_error` — error when a date edit collides.
- `indicator.card.tooltip.name_missing` — "Sin nombre" hint on tooltips.
- `common.saving`, `common.saved`, `common.save_error` — generic status hints if not already present.

### Where in code

- The two locale JSON files.

### Why

Per D08, no user-facing text is added without corresponding translations. This is standard.

### Acceptance criteria

- Every new user-visible string appears in both languages and resolves via `t()`.

---

## 11. Order of implementation

1. **Step 1 — Schema and prompt extension** (§3). Additive on the AI side; existing analyses unaffected.
2. **Step 2 — Entity extension and migration** (§4). Additive columns with defaults; existing data preserved.
3. **Step 3 — Snapshot dating logic in the worker** (§5). Behavioral change for new analyses. Verify with a fresh test PDF before proceeding.
4. **Step 4 — Add the permission** (§9).
5. **Step 5 — PATCH endpoint + service method with collision rule** (§7 backend). Behind a feature flag `ENABLE_ANALYSIS_EDIT=false` initially so the frontend can be built against it in a controlled fashion.
6. **Step 6 — History screen: warnings and inline editing** (§6, §7 frontend). Flip the feature flag to `true` when both frontend and backend are ready.
7. **Step 7 — Indicator card tooltip** (§8).
8. **Step 8 — Translations** (§10). Ideally interleaved with steps 5–7 rather than at the end.

After all eight are applied and verified end-to-end, this changeset is marked `Implemented`.

---

## 12. What this changeset does not change

- The overall flow of PDF upload → async processing → notification via header. Unchanged (D07 §5, §10).
- The three retries with exponential backoff. Unchanged (D07 §7).
- The retention or deletion behavior of analyses. Unchanged (D07 §9.3).
- The list of AI providers. Unchanged (D07 §3).
- Any spec other than D05, D07, D08, D10, D11 (via C02) — no cross-domain impact.

---

## 13. Out of scope of this changeset

- Bulk-editing the report period name across multiple analyses. Each edit is a per-analysis operation.
- Automatic detection of duplicate uploads (same report uploaded twice). The collision rule handles the date-clash symptom, not the semantic duplication.
- Timeline visualization ("show me all snapshots from Q1 reports across my holdings"). A useful future feature, not part of C05.
- Rules for editing the AI-extracted metrics themselves. Only the date and name are editable in v1; the metrics remain read-only from the AI.
