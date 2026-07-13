# Changeset C18 — Bilingual AI Executive Summary (ES/EN)

**Status:** Pending implementation
**Type:** Cross-spec changeset (feature extension + deviation from a prior explicit out-of-scope decision)
**Triggered by:** Project owner observation: the AI analysis executive summary is being stored only in English regardless of the user's UI language, and the app is bilingual (ES/EN, Spec D08). He wants the summary available in both languages and the app to show the one matching the currently selected UI language.
**Affects implementations of:** Spec D07 (AI-Powered Financial Report Analysis) — extended, not modified; Spec D08 (Internationalization) — narrows one of its explicit exclusions; Spec D10 (frontend architecture).

---

## 0. What's actually happening today (confirmed in code, not just spec)

Two separate gaps were found while investigating this request:

1. **Spec D07 §4.1 says** the executive summary should be produced *"in the user's preferred language when known, English otherwise — the language is passed into the prompt template as a variable."* **This was never implemented.** `backend/ai_extraction_prompt.md` line 21 actually says *"Write a concise executive summary... in the document's language (default English)"* — i.e. it follows the PDF's own language, not the user's. No `language`/`locale` value exists anywhere in the call chain (`asset_context` in `backend/app/worker/tasks.py`, `AIProvider.extract_from_pdf()` in `backend/app/services/ai_providers/base.py`, or the prompt template itself).
2. **Spec D08 §3.2 and §10, and D07 §13**, explicitly declared AI-generated content **frozen at generation time**: *"Switching the UI language later does not re-translate previously generated reports"* and listed *"Multi-language extraction with automatic translation of the summary"* as **out of scope for v1**.

This changeset **reverses point 2** for the `executive_summary` field specifically (and only that field — see §6) and makes point 1 moot: instead of threading a language parameter through the pipeline to generate one summary in one language, the model is asked to produce **both** languages in the same response, so the frontend can switch between them freely, including for reports the user has already seen.

---

## 1. Scope decision: one bilingual call, not two calls

Two approaches were on the table:

- **(A) Chosen — single call, dual-language fields in the same JSON response.** The extraction prompt asks the model to write the executive summary twice — once in Spanish, once in English — as two sibling fields in the same structured output it already returns. No second HTTP round-trip, no extra retry bookkeeping, no extra token cost beyond the second summary's own tokens (a few hundred, not a full second document read).
- **(B) Rejected for now — a second LLM call that translates the first summary.** This doubles per-report latency and cost (the PDF/prompt context does not need to be re-sent for a pure translation, but it is still a second network round-trip through the same provider abstraction), and requires deciding what happens when the translation call fails independently of the extraction call (a new partial-failure state that Section 7 of D07 doesn't have a slot for). It was not chosen because (A) achieves the same user-visible outcome at lower cost and complexity, consistent with D07's existing "schema-driven, data only" extension pattern (Rationale, D07 §336 area) already used for adding new indicators.

**Decision:** (A). If translation quality from asking-both-at-once ever proves worse than a dedicated translation pass, (B) remains available as a later escape hatch without touching the schema shape (just add a translation step upstream of the fields already being stored).

---

## 2. What changes in the prompt and schema

### 2.1 `backend/ai_extraction_prompt.md`

- Instruction 5 (line 21) changes from a single-language instruction to:
  > *"Write the executive summary twice, once in Spanish (`executive_summary_es`) and once in English (`executive_summary_en`), each as 3–5 bullet points conveying the same content. Both are always required, regardless of the PDF's own language — translate as needed."*
- Instruction 0's mismatch branch (line 15, `asset_match: false`) currently says "set `executive_summary` to a short note" — updated to say both `executive_summary_es`/`executive_summary_en` get the (translated) mismatch note.
- The `Required Output Format` JSON block (lines 96–125) replaces the single `"executive_summary"` key (line 111) with:
  ```json
  "executive_summary_es": "<3-5 bullet points in Spanish, each on its own line starting with •>",
  "executive_summary_en": "<3-5 bullet points in English, each on its own line starting with •>",
  ```

### 2.2 `backend/ai_extraction_schema.json`

- `required` (line 6) replaces `"executive_summary"` with `"executive_summary_es"` and `"executive_summary_en"`.
- The `executive_summary` property definition (line 79) is replaced by two sibling string properties, `executive_summary_es` and `executive_summary_en`, both required (not nullable — the model always produces both, same as today's single field is always produced).

### 2.3 What is explicitly **not** made bilingual in this changeset

`confidence_notes` and `asset_match_notes` stay single-language (whatever the model currently produces — effectively English/document-language, unchanged). Only `executive_summary` — the field the project owner actually referenced ("ese resumen") — is duplicated. Extending the same treatment to `confidence_notes` is a natural follow-up but is out of scope here to keep this changeset's blast radius small and reviewable; see §6.

---

## 3. Backend data model — `AnalysisReport` (Spec D07 §8.2)

`backend/app/db/models/ai_report.py`, class `AnalysisReport` (line 134):

- `executive_summary: Mapped[str] = mapped_column(Text, nullable=False)` (line 170) is **replaced** by two columns:
  - `executive_summary_es: Mapped[str] = mapped_column(Text, nullable=False)`
  - `executive_summary_en: Mapped[str] = mapped_column(Text, nullable=False)`

### 3.1 Migration and backfill of existing rows

Existing `analysis_reports` rows have only one summary, in whatever language they happened to be generated in (mostly English, per §0). There is no reliable way to retroactively translate them without spending a new AI call per historical row — and per D08 §10 / D07 §13's original principle, **retroactively upgrading old AI content was never promised**. The migration therefore:

1. Adds `executive_summary_es` and `executive_summary_en` as nullable.
2. Backfills both columns from the existing `executive_summary` value for every existing row (i.e., old reports show the *same, untranslated* text under both languages — a known, accepted data-quality gap for pre-changeset reports only).
3. Sets both columns `NOT NULL`.
4. Drops the old `executive_summary` column.

This is a single Alembic migration generated via `scripts/db.ps1 generate "split executive_summary into es/en"` (per [[feedback-db-script]] — migration and model change committed together).

---

## 4. Backend — response schemas and worker

- `backend/app/services/ai_providers/base.py` — `AIExtractionResult` (around line 40) gains `executive_summary_es: str` / `executive_summary_en: str` in place of `executive_summary: str`.
- `backend/app/worker/tasks.py` (line 216, where `AnalysisReport(...)` is constructed from `extracted`) — reads `extracted.get("executive_summary_es", "")` / `extracted.get("executive_summary_en", "")` instead of the single key.
- `backend/app/services/ai_report_service.py` (line 276, dict serialization) — emits both fields.
- `backend/app/api/d07_schemas.py` — `AnalysisReportSummary` (line 58) and `AnalysisReportDetail` (line 80) each replace `executive_summary: str` with `executive_summary_es: str` and `executive_summary_en: str`.
- No `language`/`locale` parameter is threaded through `extract_from_pdf()` or `asset_context` — per §0, that gap is made moot rather than fixed, since both languages are always produced in one call.

---

## 5. Frontend — language-aware display

- `frontend/src/api/types.ts` (line 298 area) — the `executive_summary: string` field on the report type is replaced by `executive_summary_es: string` and `executive_summary_en: string`.
- `frontend/src/screens/analysis-screen.ts` — both render sites (line 228, post-upload result panel; line 410, history list) switch from `r.executive_summary` to a small local helper, e.g.:
  ```ts
  const summary = currentLanguage.value === 'en' ? r.executive_summary_en : r.executive_summary_es;
  ```
  reading the existing `currentLanguage` signal from `frontend/src/state/language-state.ts` (already used by `t()` for static UI strings, per D08). Since both fields are always non-empty for reports created after this changeset, no fallback logic is needed beyond the signal read itself. For pre-changeset rows (§3.1), both fields hold identical (untranslated) text, so the switch is a no-op for old reports — consistent with D08 §3.2/§10's original "no retroactive translation" stance, now scoped down to *only* apply to reports that predate this changeset.
- No new i18n keys are needed — this is data selection, not a static UI string.

---

## 6. Deviation from Spec D08 §3.2 / §10 and Spec D07 §13 — recorded, not silently overridden

Both specs currently state, verbatim, that AI-generated content (naming `executive_summary` explicitly) is frozen at generation time and not re-translated on UI language switch, and that automatic translation of the summary is out of scope. This changeset **deliberately narrows that statement**: it no longer applies to `executive_summary` (which becomes genuinely bilingual and dynamically selected by UI language), but it **still applies** to `confidence_notes`, `asset_match_notes`, `calculations_detail`, and all other free-text AI output, which remain single-language and frozen exactly as originally specified. A future session reading D07/D08 should treat this changeset as the authoritative override for `executive_summary` only.

---

## 7. Order of implementation

1. `backend/ai_extraction_prompt.md` — dual-language instruction + output format.
2. `backend/ai_extraction_schema.json` — dual-language required fields.
3. `backend/app/services/ai_providers/base.py` — `AIExtractionResult` fields.
4. `backend/app/db/models/ai_report.py` — column split.
5. `scripts/db.ps1 generate "split executive_summary into es/en"`, review migration (backfill logic per §3.1), `scripts/db.ps1 upgrade`.
6. `backend/app/worker/tasks.py` — read both keys when building `AnalysisReport`.
7. `backend/app/services/ai_report_service.py` — serialize both fields.
8. `backend/app/api/d07_schemas.py` — `AnalysisReportSummary` / `AnalysisReportDetail`.
9. `backend/inject_ai_report.py` and `backend/tests/unit/test_prompt_builder.py`, `backend/tests/unit/test_d07_ai_extraction.py` — update fixtures/assertions to the new dual-field shape.
10. `frontend/src/api/types.ts` — type update.
11. `frontend/src/screens/analysis-screen.ts` — language-aware summary selection at both render sites.
12. Local verification: re-upload a test PDF, confirm both `executive_summary_es`/`executive_summary_en` are populated and non-empty in the DB, switch the UI language in Configuration and confirm the displayed summary changes immediately without a page reload, for both a freshly-generated report and a pre-existing (backfilled) one.
13. `frontend/src/version.ts` bump (patch segment) once committed, per [[feedback-app-versioning]].

---

## 8. What this changeset does not change

- The retry policy, job lifecycle, or provider abstraction (Spec D07 §3, §6, §7) — untouched.
- `confidence_notes`, `asset_match_notes`, `calculations_detail`, `data_provenance`, or any extracted metric — all stay exactly as they are today (single-language, frozen at generation).
- The "Definir niveles a partir de este análisis" pre-fill flow (D07 §9.1) — it already excerpts from the summary; it will now excerpt from whichever language field matches the acting user's current UI language, with no other logic change.
- Historical reports' underlying content — no retroactive AI re-analysis or re-translation is performed; only the storage shape is backfilled (§3.1).

## 9. Out of scope of this changeset

- Extending bilingual treatment to `confidence_notes` / `asset_match_notes` (§2.3) — natural follow-up, not bundled here.
- A genuine retroactive translation pass for pre-changeset reports (via a one-off script calling the translation approach from option B in §1) — could be proposed later as its own small changeset if the project owner wants old reports to read naturally in both languages too.
- Supporting a third language — D08 §3.3 only defines `es`/`en` today; adding a third would mean a third field here too, deferred until D08 itself grows a third language.
