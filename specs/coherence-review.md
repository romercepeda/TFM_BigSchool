# Specs Coherence Review — Result Report

**Date:** 2026-06-20
**Reviewer:** Systematic cross-spec audit
**Scope:** All 15 specs (6 cross-cutting engineering + 9 domain)

---

## Summary

A complete cross-spec audit identified **10 inconsistencies**, all classified by severity. All issues have been fixed in the spec files. No structural changes were needed; all fixes were localized references, missing field declarations, or obsolete forward-looking notes from earlier authoring stages.

**No contradictions in business logic were found.** The decisions are coherent across the document set.

---

## Findings

### Fixed: obsolete "to be defined" references (5 issues)

When some specs were written, others did not yet exist and were referenced as "to be defined." After completing the spec set, these references became stale.

| # | Spec | Section | Issue | Fix |
|---|---|---|---|---|
| 1 | 00a | §2 | Referenced "Spec on i18n, to be defined" | Now references Spec D08 |
| 2 | D01 | §5 (User entity) | `preferred_language` referenced "future i18n spec" | Now references Spec D08 |
| 3 | D01 | §5 (paragraph after table) | "Spec D02 — Portfolio Management, to be defined" | Now references Spec D02 |
| 4 | D03 | References header | "Spec D04 (FX Calculation Engine, to be defined)" | Now references D04 and D09 |
| 5 | D03 | §3.1 | "mechanism for resolving ticker → Asset is part of the (future) market data integration spec" | Now references Spec D09 §8 |
| 6 | D04 | §7 | "market/FX data integration layer (a separate spec, to be defined)" | Now references Spec D09 |
| 7 | D05 | References header | "Spec D07 (AI Report Analysis, to be defined)" | Now references Spec D07 |
| 8 | D06 | §5.2 | "market data layer (future spec)" | Now references Spec D09 |
| 9 | D06 | §9 | "AI analysis spec (D07, to be defined)" + obsolete promise of an AI-suggested marker field | Now references D07 §9.1 and clarifies no marker is needed (D07 decision: no specific price targets from AI) |

### Fixed: missing entity field declaration (1 issue)

| # | Spec | Section | Issue | Fix |
|---|---|---|---|---|
| 10 | D05 | §3.2 (Indicator entity) | D07 §4.2 references an `ai_extraction_key` field on each indicator, but D05's Indicator entity did not declare it | Added `ai_extraction_key` (nullable string) to the Indicator entity in D05 §3.2 |

### Fixed: enum value mismatch (1 issue)

| # | Spec | Section | Issue | Fix |
|---|---|---|---|---|
| 11 | D03 | §3.3 and §3.4 (Lot and Sale entities) | D09 §7.1 introduces enum value `manual_pending` for `fx_rate_origin`, but D03 declared the enum as `auto \| manual \| corrected` only | Added `manual_pending` to both Lot and Sale `fx_rate_origin` enum declarations, with cross-reference to D09 |

### Fixed: misleading field description (1 issue)

| # | Spec | Section | Issue | Fix |
|---|---|---|---|---|
| 12 | D05 | §3.2 | `description_key` was described as "i18n key for the user-facing description" but D08 §3.2 decided indicator descriptions remain in English in v1 (no translations) | Clarified the description_key entry in D05 to state that in v1 the resolved value is the same English description regardless of language, by explicit cross-reference to D08 §3.2 |

---

## Items intentionally left as "future spec"

These references were verified to be legitimate scope decisions, not gaps.

| Spec | Section | Note |
|---|---|---|
| D03 | §3.5 (SaleLotConsumption) | "tax/realized-gain calculations (future spec)" — confirmed: realized gain reporting is explicitly out of scope per D04 §2 and D04 §10. |
| D04 | §1 | "Calculations involving realized sales (gain/loss reporting, tax summaries) are out of scope and will be defined in a future spec." — confirmed by explicit project owner decision. |

These remain as forward-looking notes and signal that the data foundation (D03 entities Sale and SaleLotConsumption) is ready to support a future realized-gain spec without changes.

---

## Items reviewed and confirmed coherent

The following areas were systematically checked and found internally consistent across all specs:

- **Cascading deletion semantics** (D02 §8 ↔ D03 §9 ↔ D05 §9 ↔ D06 §11 ↔ D07 §12): all cascades documented atomically, with clear distinctions between holding-deletion (preserves analysis history) and portfolio-deletion (cascades through everything).
- **Daily job ownership** (D05 §6.1 ↔ D06 §5.5 ↔ D09 §6): one single daily job owns prices, indicators, and alert re-evaluation. Confirmed not split.
- **`subject_type` / `subject_id` on `IndicatorSnapshot`** (D05 §5 ↔ D07 §9.2): consistent usage and constraint statements.
- **JWT and session token references** (00b §2 ↔ D01 §5/§6): same terminology and contract throughout.
- **Redis presence** (00d §3 ↔ 00e §6 ↔ D07 §15 ↔ D09 §13): correctly introduced in 00d, environment variable declared in 00e, role explained in D07, explicitly excluded as caching layer in D09. Consistent.
- **Global configuration keys**: every config key referenced in a domain spec has a matching declaration in Spec 00f §7. Verified for `portfolios.*`, `uploads.*`, `authentication.methods.*`, `indicators.scheduled_job.*`, `alerts.*`, `ai.*`, `i18n.*`, `market_data.*`, `fx_data.*`.
- **Environment variables**: every variable referenced in domain specs (`JWT_SIGNING_KEY`, `DATABASE_URL`, `REDIS_URL`, OAuth client IDs/secrets, AI provider keys, market data API keys, `FRONTEND_BASE_URL`, `BACKEND_BASE_URL`) has a matching declaration in Spec 00e §6.
- **`fx_rate_origin` enum** across all uses: now consistent at four values (`auto`, `manual`, `corrected`, `manual_pending`).
- **Decimal precision conventions** (D04 §3.2 and downstream references in D05, D06, D09): uniformly applied; no spec contradicts the precision matrix.

---

## Conclusion

The spec set is now internally consistent. All cross-references resolve. All declared entity fields are introduced in their owning spec before being consumed elsewhere. All enums are consistent across their consumers. Configuration keys, environment variables, and external integrations are documented in a single place (Spec 00f / Spec 00e) and referenced from domain specs by name only, never duplicated.

The spec set is ready to act as the contract for implementation.
