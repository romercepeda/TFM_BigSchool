# Spec D08 — Internationalization (i18n)

**Status:** Approved
**Type:** Domain capability
**References:** Spec D01 (Authentication & Identity), Spec D02 (Portfolio Management), Spec D05 (Indicator Catalog), Spec 00a (Coding Conventions), Spec 00f (Global Configuration)

---

## 1. Purpose

Define how the application presents user-facing text, dates, and numbers in the user's preferred language and locale, while keeping all code, comments, and spec documents in English (per Spec 00a, Section 2).

This spec covers the **user-facing translation layer** only. It does not change the language of the codebase, the database schema, the API contracts, or any spec document.

---

## 2. Terminology

- **i18n** (short for **internationalization**, "i" + 18 letters + "n"): the discipline of designing the system so that adding a new language requires no code changes — only adding translation data.
- **l10n** (localization): the act of providing the actual translations and locale-specific data for one concrete language.
- **Locale**: a combination of language and regional conventions (e.g. `es-ES` Spanish from Spain, `es-MX` Spanish from Mexico, `en-US`, `en-GB`). In v1 the system tracks only the **language code** (`es`, `en`), not the regional variant — this is documented as a simplification in Section 10.

---

## 3. Scope of v1

### 3.1 What gets translated

- All static UI texts: menu labels, button captions, screen titles, table headers, form labels, validation messages, error messages, empty-state messages, confirmation dialogs, header notification text.
- The **`name_key`** of each indicator in the catalog (Spec D05 §3.2).
- The names of system enumerations shown to the user when their raw values are not user-friendly (e.g. price-level direction `buy` / `sell` → "Compra" / "Venta", `bullish` / `bearish` → "Alcista" / "Bajista").
- Date formats and number formats (per locale conventions, Section 7).

### 3.2 What does **not** get translated

- The **`description_key`** of indicators in the catalog — these remain in English in v1 by explicit decision. The UI shows the translated name alongside an English description. This trade-off is acceptable for v1; if descriptions need translation later, it is purely a matter of adding entries to the translation files.
- Asset names and tickers (`AAPL`, `Apple Inc.`) — these come from the market data layer and are presented as-is.
- Currency codes (`EUR`, `USD`) and currency symbols (`€`, `$`) — these depend on the data (the asset's quote currency, the portfolio's base currency), not on the user's language. Both currency code and symbol are presented unchanged across all languages.
- User-generated content (portfolio names, notes on price levels, notes on lots) — these are stored as written by the user and never translated.
- AI-generated content (executive summaries, confidence notes, extracted metric labels) — these are produced by the LLM in the user's preferred language at generation time (per Spec D07 §4.1) and stored as-is. Switching the UI language later does **not** re-translate previously generated reports. This was already established in D07 §13.
- Error logs, application logs, exception messages in stack traces — all remain in English to keep operational diagnostics consistent (consistent with Spec 00a).
- Spec documents and inline code comments — all in English.

### 3.3 Languages in v1

| Code | Language | Status |
|---|---|---|
| `es` | Spanish | Default. The system is shipped with Spanish as the default UI language. |
| `en` | English | Available. The user can switch to it from Configuration. |

Adding a third language is by design **a translation-data-only change**: provide the new `<locale>.json` file and add the language to the `i18n.supported_languages` configuration list (see Section 9). No code change.

---

## 4. The User's preferred language

Per Spec D01 §5, each `User` row has a `preferred_language` field, populated on account creation. Its v1 lifecycle:

- **On account creation:** set to the default value from `i18n.default_language` (Spec 00f, default `es`).
- **No automatic browser detection** in v1 (project-owner decision). The user is welcomed in Spanish by default; switching is manual from Configuration.
- **User changes language from Configuration:** the user's `preferred_language` field is updated. The change takes effect immediately on the next page render (Section 6.2).
- **Persists across sessions and devices:** the language is tied to the user, not to the device. A user who switched to English on their laptop will see English when they log in on their phone.

For unauthenticated users (the Login screen), the UI is rendered in the configured default language (`i18n.default_language`).

---

## 5. Translation file structure

### 5.1 Frontend translations

Frontend translations live in JSON files under a single folder in the frontend project:

```
frontend/src/i18n/locales/
  es.json
  en.json
```

The format is a **flat key-value structure with namespaces by dot notation**:

```json
{
  "common.button.save": "Guardar",
  "common.button.cancel": "Cancelar",
  "common.button.confirm": "Confirmar",
  "screen.dashboard.title": "Mi cartera",
  "screen.dashboard.kpi.twr": "Rentabilidad total",
  "validation.required": "Este campo es obligatorio",
  "validation.email.invalid": "Introduce un email válido",
  "validation.field_too_long": "Máximo {max} caracteres"
}
```

Placeholders use the format `{name}` (single-brace, named). Implementations interpolate at render time. Pluralization rules are out of scope for v1 (Section 10).

### 5.2 Backend translations

Backend translations live in JSON files at the backend root:

```
backend/i18n/
  es.json
  en.json
```

These cover server-generated user-facing strings: API error messages (validation errors, business rule violations), header-notification messages emitted by Celery workers, and similar. The format is identical to the frontend (flat key-value, dot-namespaced, named placeholders).

The backend chooses which language to use per request based on:
1. The authenticated user's `preferred_language` (when the request comes from an authenticated user).
2. Falling back to `i18n.default_language` for unauthenticated requests.

### 5.3 Coherence between frontend and backend

Keys are not required to overlap between frontend and backend bundles — each side owns its own strings. However, when both sides need to express the same concept (e.g. the indicator names in D05 §3.2), the **canonical key lives in the backend bundle**, because the indicator catalog is defined in the backend's seed file and the resolved name is sent to the frontend already translated.

This avoids the trap of having two independent translations of the same string drift apart.

### 5.4 Indicator name translations

The `name_key` of each indicator (e.g. `indicator.ma_200.name`, `indicator.rsi_14.name`) is resolved against the backend bundle at the moment the backend responds to a request that includes indicators. The frontend receives already-translated indicator names and renders them as opaque strings.

The same applies to indicator categorical state labels — for example, `categorical_state` indicators (D05 §4.5) declare their state strings (`golden_cross`, `death_cross`, etc.); the backend resolves these to `indicator.ma_50_200_cross.state.golden_cross` → "Golden Cross" / "Cruce dorado" at response time.

### 5.5 Missing translations

When a translation key is requested for a language that does not have it:

- The **frontend** falls back to the same key in the default language; if still missing, it renders the key itself as the visible text. This last-resort behavior is intentional: a visible raw key in production is an obvious bug signal, much better than a blank UI or a silent fallback that hides the gap.
- The **backend** follows the same fallback chain.

Missing keys are logged as warnings on the first request that needs them, then debounced to avoid log flooding.

---

## 6. Language selection at runtime

### 6.1 Resolution order

For any rendered text:

1. If the user is authenticated, use `user.preferred_language`.
2. Otherwise, use `i18n.default_language`.
3. If the chosen language is not in `i18n.supported_languages` (e.g. the user's preference was set when more languages were supported and one has since been removed from the configuration), fall back to `i18n.default_language` and log a warning.

### 6.2 How the change is propagated

When the user changes language from Configuration:

- The backend updates `user.preferred_language`.
- The backend returns the new value in the response.
- The frontend reloads its in-memory locale bundle (or fetches the new one if not yet loaded) and re-renders.
- A full page reload is **not** required.

Open browser sessions on other devices update on their next page navigation or data refresh.

---

## 7. Date and number formatting

### 7.1 Dates

Dates are formatted at the **frontend** using the browser's standard `Intl.DateTimeFormat` API, parameterized with the user's language code.

- `es` → e.g. `20/06/2026`, `20 jun 2026`.
- `en` → e.g. `06/20/2026`, `Jun 20, 2026`.

The exact display style (long, short, with month name, with weekday) is chosen by the frontend per screen but always passes the user's language to the formatter.

Times shown to the user are in the user's **browser-detected timezone**, regardless of language. Timezones are not part of the language preference. Date-only fields (e.g. `purchase_date`) are displayed without timezone interpretation.

### 7.2 Numbers and percentages

Numeric values are formatted at the frontend using `Intl.NumberFormat`, parameterized with the user's language code.

- `es` → `1.234,56`, `12,34 %`
- `en` → `1,234.56`, `12.34%`

Precision rules from Spec D04 §3.2 (e.g. 2 decimals for prices in fiat currencies, up to 8 for crypto) apply uniformly across languages; only the separator characters change.

### 7.3 Currencies

Currency display follows two independent dimensions:

- The **currency code/symbol** depends on the data (the asset's quote currency, the portfolio's base currency). It is **not** translated. A position quoted in USD is shown with `$` or `USD` regardless of the user's UI language.
- The **separators** (thousands, decimal) and the **symbol position** (before/after the number) depend on the user's language.

Example: an amount of 1234.56 USD shown to:
- A Spanish-speaking user: `1.234,56 $` (or `1.234,56 USD`)
- An English-speaking user: `$1,234.56` (or `USD 1,234.56`)

The exact rendering uses `Intl.NumberFormat` in `currency` mode with the user's language and the data's currency code.

### 7.4 Where formatting happens

All locale-sensitive formatting happens on the **frontend**. The backend always sends raw numeric values (as decimal strings to preserve precision) and ISO 8601 dates (`YYYY-MM-DD`). The backend never pre-formats numbers or dates for display.

This rule keeps the API contract locale-agnostic and means a future native mobile client could consume the same backend with its own platform's formatting conventions.

---

## 8. Translation workflow (operational)

For v1, the project owner authors translations directly in the JSON files. Suggested workflow:

1. Add the canonical key in English (`en.json`) when introducing a new UI string. English serves as the source of truth for keys.
2. Add a Spanish translation in `es.json` for the same key.
3. If a string is added to one side without the other, the missing-translation fallback (§5.5) keeps the UI functional but flags the gap.

The use of a translation-management platform (Crowdin, Lokalise, etc.) is out of scope for v1 — manual JSON file editing is sufficient at this scale. The structure does not preclude later adoption of such a platform; both Crowdin and Lokalise can ingest the JSON layout described here without changes.

---

## 9. Configuration keys (added to Spec 00f)

This spec introduces the following keys, added to Spec 00f in lockstep:

| Key | Type | Default | Description |
|---|---|---|---|
| `i18n.default_language` | string (language code) | `es` | The language used for new accounts, unauthenticated screens (e.g. Login), and as the last-resort fallback when a translation is missing. |
| `i18n.supported_languages` | list of language codes | `["es", "en"]` | The list of languages actively offered to users. The Configuration screen's language selector is populated from this list. Languages outside this list are not selectable, even if a `<locale>.json` file exists. |

Adding a third language (e.g. Portuguese) is therefore a two-step change: add `pt.json` to both frontend and backend translation folders, and add `"pt"` to `i18n.supported_languages` in `config.yaml`. Restart the application. Zero code changes.

---

## 10. Out of scope for v1

- **Regional variants** of a language (e.g. `es-ES` vs `es-MX`, `en-US` vs `en-GB`). v1 tracks only the language code. Number and date formatting will use the generic conventions for the language; subtle regional differences are accepted as a known simplification.
- **Right-to-left (RTL) languages** (Arabic, Hebrew). The application layout assumes LTR. Adding RTL would require CSS work beyond v1's scope.
- **Pluralization rules** (e.g. "1 item" vs "2 items"; languages like Russian or Polish have multi-form plurals). v1 strings are written to avoid quantity-dependent forms where possible, or accept the imperfect form.
- **Automatic browser-language detection** for new users (project-owner decision: default Spanish, manual override).
- **Translation of indicator descriptions** in the catalog (D05). Descriptions remain in English. The trade-off is documented in Section 3.2.
- **Re-translation of past AI-generated content** (D07 §13). Existing reports stay in the language they were generated in.
- **Translation of user-generated content** (notes on price levels, lot notes, portfolio names). Stored verbatim, never translated.
- **Translation-management platform integration** (Crowdin, Lokalise, etc.).
- **Per-tenant or per-user custom translations** (e.g. "use 'shares' instead of 'units' for my account"). Translations are global per language.

---

## 11. Cross-spec consistency notes

- **D01 (User entity §5):** the existing `preferred_language` field is now formally tied to this spec's `i18n.supported_languages` constraint.
- **D05 (Indicator catalog):** the indicator catalog seed file declares `name_key` (already done); D08 mandates that these keys exist in the backend translation bundles for every supported language. A missing translation produces a visible-key fallback (§5.5), not an error.
- **D07 (AI analysis):** AI-generated content is already stored in the language of generation per D07 §4.1; D08 confirms it is not re-translated.
- **00a (Coding conventions):** the rule that all code and specs are in English is reaffirmed here. The translation files are an exception, of course — they are translation **data**, not code.

---

## 12. Rationale

The two-bundle architecture (frontend bundle and backend bundle, with the backend owning catalog-driven keys like indicator names) is the simplest design that keeps the API contract locale-agnostic while letting the backend produce translated strings for data it controls. The alternative (frontend resolves all keys, including for backend-defined catalog entries) would force every catalog change to also touch the frontend — exactly the pattern the data-driven catalog (D05) was designed to avoid.

Flat JSON with dot-namespaced keys was chosen over nested JSON because flat keys diff much more cleanly in version control (a single line moves or changes per string), which matters for a project where translations are edited by hand. Nested JSON is more compact to write but causes whole-block diffs when one nested string changes, making code review and history harder.

Locale-aware formatting on the frontend (`Intl.*` APIs) avoids reinventing date and number conventions in application code. These APIs are part of every modern browser, free, well-tested, and locale-complete. The backend stays purely in raw values plus ISO dates, which is also what every API style guide recommends.

The decision to default Spanish, not auto-detect from the browser, is consistent with the project owner's profile (Spanish-speaking, primary user) and avoids a class of complaints where the auto-detected language doesn't match the user's actual preference. Manual selection is one click in Configuration.
