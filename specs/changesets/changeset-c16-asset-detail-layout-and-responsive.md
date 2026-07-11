# Changeset C16 — Asset Detail Layout Cleanup, Read-Only Processed Date, and Mobile Responsiveness

**Status:** Implemented
**Type:** Cross-spec changeset (UI/UX refinement)
**Triggered by:** Project owner review of the Asset Detail and AI Analysis screens, plus a direct check on a Samsung Galaxy Ultra–sized viewport (~412×915 CSS px) that showed the global header bar overflowing and being cut off ("Cerrar sesión" clipped at the right edge).
**Affects implementations of:** Spec D07 (AI Report Analysis) §6/§9.1, Changeset C05 §7 (inline date/name editing); Spec D10 (frontend architecture) — visual/layout only, no data model or endpoint changes.

---

## 0. How to read this document

Four independent, small UI adjustments bundled into one changeset because they were reported together and mostly touch the same two files (`asset-detail-screen.ts`, and the global `header-bar.ts`). None of them change any API contract, schema, or business logic — this is presentation-layer only.

---

## 1. Analysis history — visible, read-only "processed on" date

### What changes

Each entry in the AI Analysis history (`pi-analysis-screen`) already showed the editable **document date** (`report_date`, Changeset C05 §7 — the accounting period the report covers, user-correctable). It now also shows, directly underneath, a second, **non-editable** line: the date the analysis was actually processed (`AnalysisReport.created_at` — when the AI job completed and the report row was written).

No backend change was needed: `AiReportSummary.created_at` was already returned by `GET .../ai-reports` (it just wasn't rendered). This is purely a frontend addition.

**Sort order is unchanged** — the list is still ordered by `report_date` (Changeset C13 §3's `get_reports_for_asset`, unaffected by this changeset), not by the new processed-date line.

### Where in code

`frontend/src/screens/analysis-screen.ts` — new `.report-processed` line rendered between the editable date field and the editable name field, using `formatDate(r.created_at, { dateStyle: 'medium' })`. New i18n key `analysis.processed_date` (`es`: "Procesado el", `en`: "Processed on").

### Acceptance criteria

- Every report entry shows both "Fecha del informe: <editable>" and "Procesado el: <read-only>" — the latter has no pencil icon and no click handler.
- Editing the document date does not change the processed-on line, and vice versa (they are independent fields).
- History order is unchanged (still newest `report_date` first, per existing rule).

---

## 2. Asset Detail — "Lotes de compra" visually boxed

### What changes

The purchase-lots section now sits inside a bordered/rounded container (`.boxed-section`), matching the visual language already introduced for indicator groups in Changeset C15 — a project owner request to make it "stand out" the same way. No content or interaction changes: add/edit/delete lot flows are untouched.

### Where in code

`frontend/src/screens/asset-detail-screen.ts` — `boxed-section` class added to the lots `<div class="section">`; new `.boxed-section` CSS rule (border + padding + background, same values as `.indicator-group`).

---

## 3. Asset Detail — action buttons moved next to the asset header

### What changes

"Niveles de precio / Análisis / Editar activo / Volver / Eliminar activo" previously sat in their own row below the six summary cards. They now render alongside the ticker/name/badges block, in a shared header row (`.asset-header-row`) — right-aligned on wide screens (desktop: buttons sit at the top-right, level with "INTC"), and stacking cleanly below the name on narrow screens (mobile — see §4) rather than wrapping awkwardly at the bottom of the card grid.

### Where in code

`frontend/src/screens/asset-detail-screen.ts` — `_renderDetail()`: the `.actions` block moved inside a new `.asset-header-row` flex container alongside `.asset-header`; `justify-content: flex-end` by default, `flex-direction: column` on the row at `max-width: 639px`.

---

## 4. Mobile responsiveness pass

### What changes

Targeted fixes for the concrete overflow the project owner found at a 412×915 viewport (Galaxy S20/S21/S22 Ultra class), plus the same class of issue anywhere else it was found during verification:

- **`frontend/src/components/header-bar.ts`** (global — affects every screen): the header no longer has a fixed `height` with no wrap. It now allows wrapping (`flex-wrap: wrap`), and on screens ≤639px: button padding/font-size shrink, and the user's email/display name is hidden (the notification badge, Administration/settings/logout controls remain — those are the actions a user actually needs, the email was purely informational and was the single biggest space consumer causing the overflow). This is what was clipping "Cerrar sesión" in the reported screenshot, on **every** screen, not just Asset Detail — fixing it here fixes it everywhere at once.
- **`frontend/src/screens/asset-detail-screen.ts`**: `.content` padding shrinks on narrow screens (`--space-4` below 640px vs `--space-6` above); ticker/asset name get `overflow-wrap: anywhere` so a long name can't force horizontal scroll; both the purchase-lots and sales tables are now wrapped in a `.table-wrap { overflow-x: auto }` container so a table that's still too wide for the viewport scrolls internally instead of blowing out the page; `.asset-header-row` and `.actions` both adapt per §3.

### Where in code

`frontend/src/components/header-bar.ts`, `frontend/src/screens/asset-detail-screen.ts`. Breakpoint used is the project's existing documented `sm: 640px` (`frontend/src/styles/tokens.css`), via `@media (max-width: 639px)` — same convention already used by `portfolio-header.ts` and `landing-page.ts`.

### Acceptance criteria (verified manually via Playwright at a 412×915 viewport)

- Dashboard, Asset Detail, and AI Analysis screens all render with **zero horizontal page overflow** at 412×915 (checked via `document.documentElement.scrollWidth` vs `clientWidth`).
- The header bar's action buttons ("Administración"/"Configuración"/"Cerrar sesión") are all fully visible and tappable, not clipped, at 412px width.
- At 1280px width, the Asset Detail action buttons render top-right, level with the ticker — matching the project owner's annotated screenshot.
- Purchase lots and sales tables that would otherwise be wider than the viewport scroll horizontally within their own box instead of forcing the whole page to scroll sideways.

### What this changeset does not do

- A full site-wide responsive audit of every remaining screen (portfolios list, admin screens, settings, alerts, etc.). Those were not reported as broken and were not part of this review; each screen currently defines its own `<style>` block (Shadow DOM — no shared global stylesheet to fix once), so extending this pass to the rest of the app is a separate, larger follow-up if the project owner finds similar issues elsewhere.
- Any change to touch targets, gesture support, or a dedicated mobile navigation pattern (e.g. hamburger menu) — out of scope; the fix here is layout-only (wrapping, spacing, hiding non-essential text), not an interaction-model redesign.

---

## 5. Order of implementation

1. `frontend/src/i18n/locales/es.json`, `en.json` — `analysis.processed_date` key.
2. `frontend/src/screens/analysis-screen.ts` — read-only processed-date line.
3. `frontend/src/screens/asset-detail-screen.ts` — header/actions restructure, boxed lots section, table-wrap, responsive spacing.
4. `frontend/src/components/header-bar.ts` — wrap-friendly header, hide email on narrow screens.
5. Manual verification: Playwright at 412×915 across Dashboard/Asset Detail/AI Analysis (logged in via a real UI login, not a stubbed session), and at 1280×900 for the desktop button placement, per Spec 00c §2/§3's precedent for UI-only changes (no automated test suite covers rendered layout in this project).

## 6. What this changeset does not change

- Any API endpoint, schema, or database table.
- The `report_date` inline-editing behavior or its collision rule (Changeset C05 §7.1) — untouched, only a new adjacent read-only field was added.
- Sort order of the analysis history list.
- The Changeset C15 indicator grouping/fallback logic — reused visually (`.boxed-section` mirrors `.indicator-group`) but not modified.
