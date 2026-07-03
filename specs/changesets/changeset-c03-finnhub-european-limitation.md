# Changeset C03 — Document Finnhub free-tier limitation for European markets

**Status:** Pending implementation
**Type:** Cross-spec changeset (documentation-only)
**Triggered by:** Verification of provider free-tier coverage against actual v1 use case
**Affects implementations of:** Spec D09

---

## 0. Motivation

During a mid-implementation check against real 2026 provider terms, it was verified that **Finnhub's free tier does not include European stock market data**. Coverage of exchanges such as BME (Spain), Xetra / Frankfurt (Germany), Euronext Paris (France), and LSE (UK) requires the paid Premium plan (starting at ~$11.99/month as of the check date).

Spec D09 §3.1 currently describes Finnhub as an alternative provider with "60 API calls/minute on free tier, includes fundamentals/news" — a description that is accurate as far as it goes, but that a reader could easily interpret as "Finnhub free tier is a functional backup to Twelve Data for the same coverage." That interpretation is **wrong** for a user whose portfolio includes European equities.

The project owner has confirmed that European market coverage (specifically Spain, Germany, France, UK) is a real v1 requirement.

This changeset applies **documentation-only** clarifications so that neither the implementer nor any future reader misinterprets Finnhub's role in the current architecture.

---

## 1. Add a coverage clarification note to Spec D09 §3.1

### What changes

Modify **Spec D09 §3.1** ("Market data provider") to add a **Coverage note** immediately after the provider comparison table, stating explicitly:

> **Coverage note (v1).** Twelve Data's free tier includes international market data (European equities including BME, Xetra, Euronext, LSE — with the 4-hour delay). Finnhub's free tier is **limited to U.S. equity data**; European market coverage requires Finnhub's paid Premium plan. Therefore, in v1, Finnhub is **not a functional drop-in replacement for Twelve Data** if the portfolio contains European assets — it is a valid alternative only for U.S.-only portfolios. If the active configuration is switched to Finnhub while European holdings exist, the daily job (Section 6) will fail with "asset not found" or equivalent errors for those holdings. See Spec D12 for the European-focused provider added specifically to close this gap.

### Where in code

This is a **documentation change** to Spec D09. It is **not** implemented in code.

Because the standing rule of this project is that **original specs are not modified in place**, the change is expressed **only** as this changeset entry and is **not applied to `spec-d09-market-fx-data-integration.md` itself**. The changeset serves as the authoritative overlay: any reader consulting D09 should also consult this changeset (and C04, when it lands) for accurate operational guidance.

An index or README at the root of `specs/` should list active changesets so this indirection is discoverable.

### Why

Preventing a subtle failure mode (an operator switches to Finnhub thinking it is equivalent, and European holdings silently stop updating) is worth an explicit written warning.

### Acceptance criteria

- A reader consulting D09 §3.1 alongside this changeset can correctly answer: "Can I switch to Finnhub in v1 if my portfolio holds Santander (SAN) on BME?" → No.
- The `specs/README.md` (or equivalent index) links to this changeset.

---

## 2. Introduce a future Spec reference (D12)

### What changes

Note in D09's implicit understanding that a **new Spec D12** will be introduced to add a third provider specifically covering European markets in its free tier, targeting Spain, Germany, France, and the UK.

D12 will follow the same adapter pattern used in D09 §4 (interface `MarketDataProvider`), meaning:

- Adding the European provider is a matter of writing a third adapter class.
- The active provider selector in `market_data.provider` gains a new allowed value.
- Existing Twelve Data and Finnhub adapters are unchanged.
- The catalog of `AssetPriceHistory` records the `provider` used per data point (per D09 §5.1), so multi-provider portfolios remain auditable.

The concrete provider choice, rate limits, and any additional configuration keys will be defined in D12 itself, not here.

### Where in code

No code changes in this changeset. The reference to D12 exists only to signal the intended direction so that C03's documentation-only clarification does not read as a permanent dead-end.

---

## 3. Order of implementation

C03 has one implementation step: **add the "active changesets" index to `specs/README.md`** (or create the README if it does not exist) linking to C01, C02, and C03. Any team member reading D09 should discover this changeset from that index.

The full European-provider work belongs to Spec D12 + its own changeset (C04, to be created next).

---

## 4. Out of scope of this changeset

- Actually adding a European provider (that is Spec D12's job).
- Modifying the code of the Twelve Data or Finnhub adapters.
- Reconfiguring existing production deployments (there are none).
