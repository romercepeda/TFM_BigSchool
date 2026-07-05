# Changeset C06 — Bug fixes on the Analysis screen

**Status:** Pending implementation
**Type:** Bug-fix changeset
**Triggered by:** Regression observed while using the app: (1) the analysis history section renders but is empty even though prior analyses exist; (2) several i18n keys under `analysis.*` are rendered as raw keys instead of translated strings.
**Affects implementations of:** Spec D07, Spec D08, Spec D10 — as regressions, not as spec changes.

---

## 0. How to read this document

Unlike C01–C05, this changeset does not introduce new capability. It documents **bugs to be fixed** in the code that already implements Spec D07 (AI Analyses), Spec D08 (i18n), and Spec D10 (frontend). The behavior described here is what the specs already require; the code has drifted from them.

Because these are bug fixes, the appropriate commit prefix is `fix(...)`, not `feat(...)`.

---

## 1. Bug A — Analysis history section renders empty

### Observed behavior

On the Analysis screen (per D07 and D10 route `/portfolios/:portfolioId/assets/:holdingId/analysis`), the section titled *"Historial de análisis"* renders its header and the "Volver" button, but the list of prior analyses does not appear. The area where entries should show is blank.

### Expected behavior per specs

Per Spec D07 §9.1, the asset's analysis history must display prior `AnalysisReport`s sorted by `report_date` descending (or `created_at` if `report_date` is null), each showing report date, executive summary, global signal, extracted metrics, provider/model, and an "Eliminar análisis" action.

### Likely root causes (to be verified by the implementer, not assumed)

Based on the symptoms, one or more of the following:

1. **Frontend fetch failure silently swallowed.** The `pi-analysis-screen` component may be calling the analyses list endpoint but discarding errors instead of surfacing them. Check `frontend/src/screens/analysis-screen.ts` and `frontend/src/api/analyses.ts`.
2. **Backend endpoint returning empty list where it should not.** The `GET /analyses?holding_id=...` endpoint may be filtering by wrong criteria after some recent change (e.g. adding a `status = succeeded` filter that also excludes rows that should be shown). Check `backend/app/api/analyses.py`.
3. **Data-scope mismatch.** After C02 introduced RBAC (D11), the analyses listing may be filtering by user/permission in a way that excludes legitimately visible reports. Check whether the endpoint uses the correct ownership filter (the holding must belong to a portfolio owned by the current user).
4. **Signal not subscribed / render not triggered.** If a signal was recently added around this screen, its `effect()` wiring may be misconfigured — the API call may run, data may arrive, but the component may not re-render.

### Where in code to investigate first

- `frontend/src/screens/analysis-screen.ts` — verify: is `renderHistory()` called from an `effect()`? Does it read from a signal that was populated after the API call?
- `frontend/src/api/analyses.ts` — verify: is the error being caught and printed to console but not surfaced? Are all analyses returned by the backend actually parseable into the frontend model shape?
- `backend/app/api/analyses.py` — verify: the list endpoint returns rows for the holding regardless of status, and applies only the ownership check per Spec 00b §5.
- Browser DevTools Network tab: is the request actually being made? What does the response body look like?

### Diagnostic-first approach (required)

**The implementer must not "guess and patch."** Before writing any fix, they must:

1. Reproduce the bug on a local install with at least one existing analysis for a test asset.
2. Report back with: (a) whether the request is made; (b) the exact response body; (c) whether the console shows any errors; (d) whether the component render path receives the data.
3. Only after the root cause is identified, propose the fix.

### Acceptance criteria

- On a fresh install with at least one existing `AnalysisReport` for a holding, the Analysis screen shows the entry in the "Historial de análisis" section.
- Errors in the fetch path are surfaced to the UI (empty state message: *"No se pudieron cargar los análisis previos"*), not silently swallowed.
- Regression test added: a component test in `frontend/tests/screens/analysis-screen.test.ts` verifies that when the mocked API returns a non-empty list, the history section renders exactly N entries.

---

## 2. Bug B — Raw i18n keys visible on the Analysis screen

### Observed behavior

The Analysis screen shows the following raw i18n keys instead of translated text:

- `analysis.title` (header of the screen)
- `analysis.uploading` (upload area primary text)
- `analysis.or_click` (upload area secondary text)
- `analysis.history` (history section header)

Per Spec D08 §5.5, when a key is missing from the loaded locale bundle, the frontend falls back to the default-language bundle, and only when it is missing there does it render the raw key. The fact that raw keys are visible means the key is missing from **both** `es.json` and `en.json` — the bundle has drifted from the code.

### Expected behavior per specs

Per Spec D08 §5.1, every user-facing string flows through `t(key)`, and every referenced key must be present in both language bundles.

### Where in code to fix

- **`frontend/src/i18n/locales/es.json`** — add the four missing keys with Spanish translations.
- **`frontend/src/i18n/locales/en.json`** — add the same keys with English translations.

Suggested values:

| Key | Spanish | English |
|---|---|---|
| `analysis.title` | Análisis IA | AI Analysis |
| `analysis.uploading` | Arrastra un PDF aquí | Drop a PDF here |
| `analysis.or_click` | o haz clic para seleccionar | or click to select |
| `analysis.history` | Historial de análisis | Analysis history |

The implementer must **also grep the frontend codebase** for other `analysis.*` keys referenced in code but missing from the bundles. Any additional missing keys must be added in the same commit.

### Why

Per Spec D08, the visible-raw-key fallback is a bug signal, not a normal state. The fact that it appears means the translation bundle was not updated when the screen was implemented, which is a Spec D08 §5.5 violation.

### Acceptance criteria

- Loading the Analysis screen in Spanish shows: *"Análisis IA"*, *"Arrastra un PDF aquí"*, *"o haz clic para seleccionar"*, *"Historial de análisis"*.
- Loading the same screen in English shows the English equivalents.
- A grep of `frontend/src/` for `t\(['"]analysis\.` returns no keys that are missing from the two locale bundles.

---

## 3. Preventive: add a startup check for missing i18n keys (Spec D08 §5.5 enforcement)

### What changes

Add a **build-time validator** that greps the frontend source for every `t('...')` call and verifies that every referenced key exists in both `es.json` and `en.json`. Missing keys cause the build to fail with a clear error listing every missing key and its source file location.

### Where in code

- **`frontend/scripts/validate-i18n.mjs`** — a small script that walks `src/`, extracts `t('key')` calls with a regex, and validates against the JSON files.
- **`frontend/package.json`** — add `validate:i18n` script; make it run automatically before `build` and as part of `test`.
- **CI configuration** (when CI is set up per Spec 00d §5): invoke `npm run validate:i18n` on every push.

### Why

Bug B is a symptom of a deeper issue: nothing prevents a developer from adding `t('some.new.key')` to a component without also adding the key to the JSON bundles. A build-time check turns "visible in production" into "build fails locally," which is where the friction should be.

This is a small preventive investment that pays for itself the first time it catches a real drift, and directly implements the spirit of Spec D08 §5.5 (which says the raw-key fallback is intended as a "bug signal" — but only useful if the developer sees it before the user does).

### Acceptance criteria

- Running `npm run validate:i18n` on the current codebase (after fixing Bug B) exits cleanly.
- Removing a key from `es.json` and running the script exits with an error listing the missing key and the file(s) that reference it.
- Adding a new `t('new.key')` in a component without adding the key to the JSON bundles causes `npm run build` to fail.

---

## 4. Order of implementation

1. **Diagnose Bug A** per §1: reproduce, capture evidence, identify root cause. Report back.
2. **Fix Bug B** per §2. This is a straightforward JSON edit and can happen in parallel with the diagnostic phase of §1.
3. **Fix Bug A** based on the diagnosis. Include the regression test in the same commit.
4. **Add the i18n validator** per §3. Include a passing run in the same commit.

Suggested commits:

- `fix(i18n): add missing analysis.* translation keys (Bug B)`
- `fix(analysis): restore history rendering on Analysis screen (Bug A)`
- `test(analysis): add regression test for history rendering`
- `chore(i18n): add build-time i18n key validator`

---

## 5. What this changeset does not change

- No new specification behavior. Everything here is bringing the code back to what D07, D08, and D10 already require.
- No new database migrations, no new endpoints, no new UI screens. Only fixes to existing code.
- No changes to backend business logic beyond what is needed to correctly return the analyses list (if that turns out to be the root cause of Bug A).

---

## 6. Coordination with C05

C05 (editable date and name on analyses) will add new fields to the analysis history entries. **C06 must be applied first** so that C05 has a working history section to render its warnings and inline editors into. Attempting to apply them in the opposite order would leave the C05 UI attached to an invisible container.
