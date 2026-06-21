# Spec D07 — AI-Powered Financial Report Analysis

**Status:** Approved
**Type:** Domain capability
**References:** Spec D03 (Asset Holdings), Spec D05 (Indicator Catalog & Historical Snapshots), Spec D06 (Price Levels), Spec 00b (Security Practices), Spec 00f (Global Configuration)

---

## 1. Purpose

Allow a user to upload a financial report (PDF) for a specific asset, have it processed asynchronously by an external Large Language Model (LLM), and obtain structured outputs that:

1. Feed the **fundamental indicators** defined in Spec D05 (PER, ROE, Debt/EBITDA, Revenue Growth YoY, Analyst Sentiment, and any future indicators added to the catalog).
2. Produce a human-readable **executive summary** of the report.
3. Produce a **global signal** classification (bullish / neutral / bearish).
4. Are preserved as an immutable record of the analysis (an `AnalysisReport`), shown in the asset's "Historial" view.

The spec covers the **manual PDF upload** path in v1. The architecture is deliberately designed so that adding future ingestion sources (web-scraping, news feeds, automated periodic pulls) does not require redesigning the user-facing flow or the storage model.

---

## 2. Conceptual model

Three entities, with distinct responsibilities:

1. **`AnalysisJob`** — the asynchronous unit of work. Tracks the lifecycle (queued → running → succeeded / failed) and retry attempts. Disposable: once the corresponding report is materialized successfully, the job's value is operational only.
2. **`AnalysisReport`** — the materialized outcome. An immutable record (within the user-deletable rule of Section 9.3) of one analyzed report: the source PDF reference, the extracted structured data, the executive summary, the signal, and links to the indicator snapshots it produced.
3. **`UploadedFile`** — the storage of the original PDF, kept for re-processing and audit.

The pipeline is: **upload** → `UploadedFile` created → `AnalysisJob` queued → Celery worker picks up → calls the configured AI provider → on success, `AnalysisReport` is created + `IndicatorSnapshot`s are written + the job is marked succeeded → on failure, the job is retried up to 3 times with exponential backoff.

---

## 3. AI provider abstraction (multi-provider support)

The system is designed to support **three LLM providers** (Anthropic Claude, OpenAI GPT, Google Gemini), with the active provider chosen per the global configuration. Adding a fourth in the future is a matter of writing a new adapter, not changing business logic.

### 3.1 Adapter interface

A single Python interface (`AIProvider`) is defined in the backend, with one abstract method:

```python
extract_from_pdf(
    pdf_bytes: bytes,
    prompt_template: str,
    schema: dict,  # JSON schema the response must conform to
    asset_context: dict,  # ticker, name, asset_type, quote_currency
) -> AIExtractionResult
```

`AIExtractionResult` is a structured object containing the parsed JSON, the raw response (for audit), the provider used, the model version used, and a `parse_status` indicating whether the response validated cleanly against the schema.

### 3.2 Concrete adapters

Three implementations exist:

- `AnthropicProvider` — uses the Anthropic Messages API with PDF document support and the model identifier from configuration.
- `OpenAIProvider` — uses the OpenAI Responses API with PDF support.
- `GeminiProvider` — uses the Google Gemini API with PDF document support.

Each adapter:
- Handles the provider-specific request shape (how the PDF is attached, how the system/user prompts are structured, how structured-output mode is requested).
- Normalizes the provider's response into `AIExtractionResult`.
- Surfaces provider-specific errors (rate-limit, timeout, malformed response) as a common error type so the retry logic in Section 7 is provider-agnostic.

### 3.3 Provider selection

The active provider is determined at runtime by the configuration key `ai.provider` (see Spec 00f addition in Section 14). Allowed values in v1: `anthropic` \| `openai` \| `gemini`. The factory resolves the value to the corresponding adapter at the moment an `AnalysisJob` starts processing.

Each provider has its own model identifier and API-key environment variable (see Section 14 and Spec 00e). The system never logs, persists, or echoes API keys.

### 3.4 Out-of-scope: per-job provider override, multi-provider voting

In v1, the active provider applies to all analyses globally. A user cannot pick a provider per upload. Cross-provider consensus (e.g. running the same PDF through all three and comparing) is not supported.

---

## 4. The prompt and extraction schema

### 4.1 Configurable prompt template

The prompt sent to the LLM is **not hardcoded** in application code. It lives in a versioned file at the backend root: **`ai_extraction_prompt.md`** (Markdown, for readability and version-control diffs).

The prompt is loaded at application startup and held in memory; changes require a restart, consistent with the broader configuration-loading discipline.

The prompt instructs the model to:
- Read the attached PDF in its entirety.
- Produce a **strict JSON object** conforming to the schema in Section 4.2.
- Use `null` for any field whose value cannot be confidently determined from the document.
- Provide concise textual fields (summary, sentiment justification) in the user's preferred language when known, English otherwise — the language is passed into the prompt template as a variable.

### 4.2 Extraction schema

The JSON schema the LLM's response must conform to is defined and version-controlled in the file **`ai_extraction_schema.json`**. The v1 shape:

```json
{
  "report_date": "string (ISO 8601 date, YYYY-MM-DD) | null",
  "metrics": {
    "per": "number | null",
    "roe": "number | null",
    "debt_ebitda": "number | null",
    "revenue_growth_yoy": "number | null",
    "analyst_sentiment": "bullish | mixed | bearish | null"
  },
  "executive_summary": "string (3-5 bullet points)",
  "global_signal": "bullish | neutral | bearish | null",
  "confidence_notes": "string | null"
}
```

The keys under `metrics` correspond exactly to the `ai_extraction_key` declared by each fundamental indicator in the seed file `indicators_catalog.yaml` (D05 §3.1). This is the linkage that lets the indicator catalog grow without code changes: when a new fundamental indicator is added to the seed file with a new `ai_extraction_key`, the schema is updated to include that key, the prompt is updated to ask for it, and the system automatically routes the extracted value into a snapshot for that indicator. Only the schema and prompt change; no code does.

### 4.3 Response validation

When the LLM responds, the adapter parses the JSON and validates it against `ai_extraction_schema.json` using Pydantic. Any of the following constitute a **schema-validation failure**:

- Response is not valid JSON.
- Required fields are missing entirely (versus present-but-null, which is acceptable).
- A field has the wrong type (e.g. a string where a number is expected).
- An enum-typed field has a value outside its allowed set.

A schema-validation failure causes the job to fail (Section 7) and the response is recorded in the `AIExtractionResult.raw_response` for diagnosis.

### 4.4 Missing metrics policy

If the LLM legitimately returns `null` for one or more metrics under `metrics` (i.e. the PDF did not contain that information), the system:

- Stores the metric as `null` on the `AnalysisReport`.
- **Still creates** an `IndicatorSnapshot` for the corresponding indicator, with `value_numeric = null` (or `value_text = null` for categorical). The UI shows "sin dato" for that indicator at that date.
- Does **not** treat the analysis as failed. A partial extraction is a valid extraction.

This is consistent with D05's principle of explicit absence over silent zero.

---

## 5. Upload flow (user-facing)

UI screen: "Análisis IA de informe" (Screen 8 in the functional design).

1. User selects an asset whose holding is in their currently selected portfolio.
2. User drags a PDF onto the upload area or clicks to pick one.
3. Frontend uploads the file to the backend endpoint. The endpoint validates:
   - File type is PDF (validated by content sniffing, not just extension — per Spec 00b §4).
   - File size is ≤ `uploads.max_file_size_mb` (Spec 00f §7.2).
4. Backend creates the `UploadedFile` row (Section 8.1) and enqueues an `AnalysisJob` (Section 6.1).
5. Backend returns immediately to the frontend with a confirmation: *"Tu informe se está procesando en segundo plano. Te avisaremos en la cabecera cuando esté listo."*
6. The user can keep navigating. A banner / notification appears in the app's header when one or more jobs transition to `succeeded` or `failed` (Section 10).

The user is **not** blocked waiting for the LLM. This is the asynchronous flow chosen explicitly per the project owner's decision.

---

## 6. `AnalysisJob` entity

The asynchronous unit of work. Tracked in the database; orchestrated by Celery.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. Also the Celery task correlation id. |
| `holding_id` | UUID | Foreign key to `Holding` (D03). |
| `uploaded_file_id` | UUID | Foreign key to `UploadedFile` (Section 8). |
| `provider` | enum | `anthropic` \| `openai` \| `gemini`. Captured at the moment processing starts (not at upload), so a change of provider between upload and processing is reflected. |
| `model_version` | string, nullable | The provider's model identifier used (e.g. `claude-opus-4-7`). Populated on first run attempt. |
| `status` | enum | `queued` \| `running` \| `succeeded` \| `failed`. |
| `attempt_count` | integer | Starts at 0; increments before each retry. |
| `last_error` | text, nullable | Truncated error message of the most recent failure. |
| `analysis_report_id` | UUID, nullable | Set when `status = succeeded`; foreign key to `AnalysisReport`. |
| `created_at` | timestamp (UTC) | When the job was enqueued. |
| `started_at` | timestamp (UTC), nullable | When the worker picked it up for its first attempt. |
| `completed_at` | timestamp (UTC), nullable | When it reached `succeeded` or `failed`. |

### 6.1 Lifecycle

- **Enqueue:** an HTTP request from the upload endpoint creates the row with `status = queued` and pushes a corresponding task onto Celery.
- **Pick-up:** a Celery worker fetches the task, marks the job `running`, increments `attempt_count`.
- **Execute:** the worker resolves the active provider (Section 3.3), loads the PDF bytes from `UploadedFile`, calls `extract_from_pdf`, validates the response against the schema.
- **Success:** the worker creates an `AnalysisReport` (Section 8.2), writes the linked `IndicatorSnapshot`s for fundamental indicators per D05 §6.2, marks the job `succeeded`, links `analysis_report_id`, sets `completed_at`.
- **Failure:** the worker captures the error, writes `last_error`, decides between retry (Section 7) or final failure.

---

## 7. Retry policy

Retries apply to any failure during the worker run: HTTP errors against the provider (rate-limit `429`, server errors `5xx`, network timeouts), schema-validation failures (Section 4.3), and provider-internal errors. Validation failures are also retried because a different sampling of the model frequently produces well-formed JSON.

- **Maximum attempts:** 3 total (initial + 2 retries).
- **Backoff between attempts:** 1 minute → 5 minutes → 15 minutes (exponential).
- **After the third failed attempt:** `status = failed`, `last_error` retained, `completed_at` set. The user sees this in the header notification.
- **Per-attempt timeout:** configurable globally (Section 14). Default 120 seconds per LLM call.

Schema-validation failures and JSON-parse failures are **not** retried infinitely — they consume one of the three attempts.

Errors caused by configuration problems (no API key, unknown provider, model not available) **do not retry** because they will repeat identically; they go straight to `failed`.

---

## 8. Storage entities

### 8.1 `UploadedFile`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `user_id` | UUID | Foreign key to `User` (D01). The original uploader. |
| `original_filename` | string | As provided by the browser. Free-form. |
| `mime_type` | string | Verified at upload. v1: only `application/pdf`. |
| `size_bytes` | integer | |
| `content` | BYTEA | The raw file bytes, stored in PostgreSQL per project owner's decision. The implications (DB size growth, slower backups) are knowingly accepted. |
| `created_at` | timestamp (UTC) | |

`UploadedFile` rows are referenced by `AnalysisJob.uploaded_file_id`. The same file is referenced by at most one job in v1; re-running an analysis with the same PDF creates a new `UploadedFile` row (this is a deliberate simplification — deduplication would require content-hash comparison and is not justified for v1).

### 8.2 `AnalysisReport`

The materialized outcome of a successful analysis. Immutable except for user-initiated deletion (§9.3).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `holding_id` | UUID | Foreign key to `Holding`. |
| `uploaded_file_id` | UUID | Foreign key to `UploadedFile`. |
| `analysis_job_id` | UUID | Foreign key to the job that produced it. |
| `report_date` | date, nullable | The date of the financial report itself (when the LLM identified it). Used as the `as_of_date` for the linked `IndicatorSnapshot`s. If null, the job's `completed_at` date is used. |
| `provider` | enum | Same as `AnalysisJob.provider`. |
| `model_version` | string | The model used. |
| `extracted_metrics` | JSONB | The full `metrics` block returned by the LLM. |
| `executive_summary` | text | |
| `global_signal` | enum | `bullish` \| `neutral` \| `bearish` \| null. |
| `confidence_notes` | text, nullable | |
| `raw_response` | JSONB | The full LLM response, for audit. |
| `created_at` | timestamp (UTC) | |

---

## 9. Display, history, and deletion

### 9.1 Display on the asset detail view

The Asset Detail screen (Screen 6) lists `AnalysisReport`s for the holding under the "Historial" tab, sorted by `report_date` descending (falling back to `created_at` if the report date is missing). Each entry shows: the report date, the executive summary, the global signal, the extracted metrics, the provider/model used, and an "Eliminar análisis" action.

Per the existing functional design, the AI analysis screen offers a "Definir niveles a partir de este análisis" action that pre-fills the define-levels form (Spec D06 §9) with values suggested from the analysis. In v1, the suggestions are conservative: the form is pre-filled with the asset's current price plus a structured note that includes the report's signal and a brief excerpt from the summary. The LLM is **not** asked to suggest specific price targets in v1; doing so reliably is beyond the scope of the prompt and would require a separate research effort. This is captured in Section 13 as out-of-scope.

### 9.2 Link to indicator snapshots

When an `AnalysisReport` is created, one `IndicatorSnapshot` row is created per fundamental indicator extracted, with:
- `indicator_id` resolved by `ai_extraction_key` → indicator catalog mapping.
- `subject_type = asset`, `subject_id = holding.asset_id`.
- `as_of_date = AnalysisReport.report_date` (or fallback per §8.2).
- `value_numeric` or `value_text` populated, or `null` per §4.4.
- `source = ai_analysis`, `source_ref = AnalysisReport.id`.

Per D05 §5, a re-analysis with the same `as_of_date` updates the snapshot rather than duplicating it.

### 9.3 Deletion of an analysis

The user can delete an `AnalysisReport` from its detail view in the historial. The deletion is **hard delete** and atomic within a single transaction. It cascades to:

- The `AnalysisJob` (the job and the report are conceptually a single unit).
- The corresponding `UploadedFile` (the stored PDF is no longer needed if the analysis is removed).
- The `IndicatorSnapshot`s whose `source = ai_analysis` and `source_ref` matches the deleted report's id (the indicator history derived from this analysis disappears).

This is consistent with the user's stated need to be able to discard mistaken or low-quality analyses without leaving residual artifacts. It differs intentionally from D06's price-level history rule (which is fully immutable): in D07, the entire AI analysis is a single user-driven artifact and the user owns the right to remove it.

The user is asked to confirm before deletion, with the confirmation stating that the linked indicator snapshots derived from this analysis will also disappear.

---

## 10. Header notifications

When one or more `AnalysisJob`s of the current user transition to `succeeded` or `failed`, a small notification appears in the application's header (per the project owner's chosen UX). The notification:

- Shows a count of completed jobs since the user last acknowledged.
- On click, opens a panel listing recently completed jobs with their outcome and a link to the relevant asset.
- Persists until the user acknowledges (closes the panel).

The notification system is intentionally lightweight in v1: no push notifications, no email — only the in-app header indicator.

How the frontend learns about completed jobs: the frontend polls a backend endpoint at a low frequency (configurable globally — Section 14, default 30 seconds) for the user's recent job status changes. Push from server to client (WebSocket) is out of scope for v1.

---

## 11. Authorization and isolation

- A user can only upload PDFs against holdings whose parent portfolio belongs to them (Spec 00b §5).
- A user can only see and delete `AnalysisReport`s and `UploadedFile`s they themselves created.
- The PDF content is **never shared** between users in v1, even if two users analyze the same report — each upload is a separate `UploadedFile`.

---

## 12. Cross-spec cascading

- When a `Holding` is deleted (D03 §6.3): all of its `AnalysisJob`s, `AnalysisReport`s, related `UploadedFile`s, and `ai_analysis`-sourced `IndicatorSnapshot`s are deleted in cascade.
- When a `Portfolio` is **archived** (D02 §6): existing analyses are preserved but new uploads are rejected against assets of the archived portfolio. Re-activating the portfolio restores upload capability.
- When a `Portfolio` is **permanently deleted** (D02 §8): all related entities cascade as part of the same operation already defined in D02.

---

## 13. Out of scope for v1

- **Automated periodic ingestion** (web-scraping, news feeds, EDGAR pulls). The architectural separation between upload source and analysis pipeline preserves the path to adding these later without UI changes.
- **AI-suggested specific price targets** based on the analyzed report. The LLM produces sentiment and metrics; price-target estimation is a separate research problem.
- **Cross-provider consensus** or per-job provider selection by the user.
- **Multi-language extraction with automatic translation** of the summary. The summary is produced in the user's preferred language as known at extraction time; switching the UI language later does not re-translate existing reports.
- **De-duplication of uploads** by content hash.
- **Streaming responses** from the LLM to the user. v1 always shows a "processing" state until the entire job completes.
- **Reprocessing UI** that takes an existing `UploadedFile` and runs a new analysis without re-uploading. The data model supports it (the PDF is stored), but the UI surface is deferred.
- **Detailed usage/cost telemetry** per provider (tokens consumed, monetary cost). The provider's own dashboard is the authoritative source in v1.

---

## 14. Configuration keys (added to Spec 00f)

This spec introduces the following keys, added to Spec 00f in lockstep:

| Key | Type | Default | Description |
|---|---|---|---|
| `ai.provider` | enum (`anthropic` \| `openai` \| `gemini`) | `anthropic` | The active LLM provider used for PDF analyses. |
| `ai.anthropic.model` | string | `claude-opus-4-7` | Model identifier for the Anthropic adapter. |
| `ai.openai.model` | string | `gpt-4o` | Model identifier for the OpenAI adapter. |
| `ai.gemini.model` | string | `gemini-2.5-pro` | Model identifier for the Gemini adapter. |
| `ai.per_call_timeout_seconds` | integer ≥ 1 | `120` | Per-attempt LLM call timeout. |
| `ai.notifications.poll_interval_seconds` | integer ≥ 5 | `30` | Frontend polling interval for completed-job notifications. |

The retry policy itself (3 attempts, 1m/5m/15m backoff) is not configuration — it is part of the engineering contract and not exposed via `config.yaml`. If the project owner ever needs to tune it, that becomes a code/spec change.

Three new environment variables are added to Spec 00e (Prerequisites & Manual Setup):
- `AI_ANTHROPIC_API_KEY`
- `AI_OPENAI_API_KEY`
- `AI_GEMINI_API_KEY`

At least one must be set for the active provider; an unset variable for an inactive provider does not block startup.

---

## 15. Rationale

The asynchronous Celery+Redis architecture was chosen over FastAPI `BackgroundTasks` because each PDF analysis consumes meaningful money in tokens, and losing an in-flight job to a server restart would be both wasteful and confusing. Celery + Redis is the industry-standard pattern for this exact use case, with mature retry, monitoring, and observability primitives.

The multi-provider adapter pattern is more code than picking one provider, but the project owner explicitly requested it. The marginal cost is small (three thin classes implementing the same interface) and the benefit is real: the project owner can swap providers without redeploying the application's business logic, which mirrors the broader portability theme (Docker, no managed identity service, no managed DB).

Storing PDFs as PostgreSQL BYTEA was accepted with explicit knowledge of the implications. For a personal-use MVP analyzing dozens to low hundreds of reports per year, the impact is acceptable. The architectural escape hatch — refactoring later to a separate file store — is preserved by isolating storage behind the `UploadedFile` entity; a future refactor only touches that table's `content` column, not the rest of the system.

The schema-driven prompt is the design decision that gives D07 its claim to "data-driven, no code change to extend." A new fundamental indicator becomes a new line in the indicator seed file, a new key in the JSON schema, and a new instruction in the prompt — three configuration changes, zero code changes. This is the same pattern as D05 and is intentional consistency.

The decision to **let the user delete analyses** (unlike D06's fully immutable history) reflects a key difference between the two domains: D06 records the user's own thinking (which they should not silently overwrite); D07 records the output of an external tool whose quality the user must be free to judge and discard. Conflating the two would either harm history integrity in D06 or trap users with bad LLM outputs in D07.
