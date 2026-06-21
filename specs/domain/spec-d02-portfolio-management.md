# Spec D02 — Portfolio Management

**Status:** Approved
**Type:** Domain capability
**References:** Spec D01 (Authentication & Identity), Spec 00b (Security Practices)

---

## 1. Purpose

Allow an authenticated user to create, view, rename, archive, restore, and permanently delete portfolios. Each portfolio is an isolated container of assets denominated in a single base currency, against which all portfolio-level returns are calculated.

This spec defines the lifecycle and rules of the Portfolio entity itself. It does **not** cover the assets, purchase lots, indicators, or analyses contained within a portfolio — those are defined in their own domain specs.

---

## 2. Portfolio entity

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key, auto-generated. Never visible to the user. |
| `user_id` | UUID | Foreign key to the owning `User`. |
| `name` | string | Display name. Editable. Not unique — see Section 4. |
| `base_currency` | string (ISO 4217 code) | One of: `EUR`, `USD`, `GBP`, `JPY`, `CHF`, `CAD`, `AUD` in v1. **Immutable after creation.** |
| `status` | enum | `active` or `archived`. Default: `active`. |
| `created_at` | timestamp (UTC) | Auto-set on creation. |
| `updated_at` | timestamp (UTC) | Auto-updated on any modification. |
| `archived_at` | timestamp (UTC), nullable | Set when archived; null when active. Cleared if restored. |

---

## 3. Creation

A user can create a portfolio by providing:
- **Name** (required, non-empty string).
- **Base currency** (required, selected from the v1 list above).

On creation:
- A new `Portfolio` is persisted with `status = active`.
- The user is informed during the creation flow that **the base currency cannot be changed later**.
- If the user reaches the **per-user portfolio limit** (see Section 9), creation is rejected with a clear error message.

---

## 4. Naming rules

- Portfolio names are **display labels**, not identifiers. The internal identifier is always the UUID.
- Two portfolios belonging to the same user **may share the same name**, regardless of their `status`. The system does not enforce name uniqueness.
- The name can be edited at any time while the portfolio is `active`. Archived portfolios cannot be renamed (must be restored first).
- Name length is constrained by a maximum (configurable globally, see Section 9); content otherwise unrestricted (any Unicode allowed for i18n).

---

## 5. Immutability of base currency

- Once a portfolio is created, its `base_currency` is **immutable** — there is no UI control or API endpoint that allows changing it.
- Rationale: every historical KPI (TWR, CAGR, Drawdown, Volatility, Sharpe) for this portfolio is calculated and stored in this base currency. Allowing a change would require either recomputing the entire history with new exchange rates (expensive and ambiguous for past dates) or invalidating the history (which the user did not intend by simply switching currency).
- If the user effectively needs a portfolio in a different base currency, they create a new portfolio and decide manually how to populate it.

---

## 6. Archiving (soft delete)

A portfolio can be **archived** from its active state. Archiving is the v1 equivalent of "deleting" a portfolio from the user's main view.

On archive:
- `status` is set to `archived`.
- `archived_at` is set to the current UTC timestamp.
- The portfolio disappears from the main "My Portfolios" list and from the portfolio selector in the Dashboard.
- All its assets, purchase lots, price levels, and analyses are **preserved untouched** in the database. They are not deleted, only made invisible by the parent portfolio's status.
- These entities are **excluded from any calculation** in other screens (e.g. cross-portfolio aggregates, if any are added later).
- The portfolio counts against the user's portfolio limit (Section 9) **only if it is active** — archived portfolios do not consume the active quota.

---

## 7. Restoration

An archived portfolio can be **restored** from the "Archived portfolios" section.

On restore:
- `status` is set back to `active`.
- `archived_at` is cleared (set to null).
- All previously preserved assets, lots, price levels, and analyses become visible again and re-enter the relevant calculations exactly as they were before archiving.
- Restoration is rejected if it would cause the user to exceed the per-user portfolio limit (Section 9). The user is informed and must archive another active portfolio first, or proceed with a permanent delete instead.

---

## 8. Permanent deletion (hard delete)

A portfolio can be **permanently deleted** from the "Archived portfolios" section. A portfolio cannot be permanently deleted directly from the active state — it must be archived first. This two-step process exists deliberately to prevent accidental loss.

On permanent delete:
- The portfolio record is removed from the database.
- **Cascading delete:** all related entities owned by this portfolio are also deleted in the same transaction. This includes (but is not limited to): assets/holdings, purchase lots, price levels, analysis records, historical indicator values, and any portfolio-specific settings. The exact list is determined by the foreign-key relationships defined in the technical schema spec.
- The operation is atomic: either everything is deleted or nothing is.
- Before deletion is confirmed, the user **must confirm explicitly** through a confirmation prompt that states the operation cannot be undone.
- No record of the deleted portfolio is preserved in v1 (no audit log, no soft-tombstone). This is consistent with the equivalent decision in Spec D01 for guest account migration (hard delete, no trace).

---

## 9. Per-user limits

The maximum number of **active** portfolios per user is **configurable globally** via the configuration mechanism defined in Spec 00f (Global Application Configuration). The relevant keys are:

- `portfolios.max_active_per_user` — maximum number of active portfolios per user. Default in v1: 10.
- `portfolios.name_max_length` — maximum length of a portfolio name. Default in v1: 60.

Archived portfolios do not count against the active-portfolio limit. The limit is checked on creation (Section 3) and on restoration (Section 7). When the limit is reached, the user receives a clear error message explaining the cap and how to free a slot (archive an existing portfolio).

The portfolio name length limit is enforced at creation (Section 3) and on rename (Section 4).

---

## 10. Functional flow (UI references)

The following user flows correspond to existing screens in the functional design:

| Action | Screen(s) involved |
|---|---|
| Create portfolio | Login → My Portfolios → Create portfolio |
| Select portfolio to work on | My Portfolios → Dashboard (or directly from Dashboard's selector when the user has multiple) |
| Rename | Configuration → Manage portfolios (or inline edit on My Portfolios) |
| Archive | Configuration → Manage portfolios, or from the portfolio's own settings |
| View archived | Configuration → Archived portfolios |
| Restore | Archived portfolios → Restore action on a specific portfolio |
| Permanently delete | Archived portfolios → Delete action on a specific portfolio (with confirmation) |

Post-login routing (per Spec D01, Section 6, step 8): if the user has **2+ active portfolios**, they land on "My Portfolios"; if exactly **1 active portfolio**, they land directly on its Dashboard; if **0 active portfolios** (e.g. a brand-new user or one who just archived all of theirs), they land on "Create portfolio".

---

## 11. Authorization

Per Spec 00b, Section 5: a user can only see and modify portfolios where `user_id` matches their own authenticated identity. This applies to active and archived portfolios alike. No portfolio is ever shared between users in v1.

---

## 12. Out of scope for v1

- Sharing a portfolio with another user (read or write).
- Cross-portfolio consolidated views (e.g. an aggregated total in a chosen "report currency" across portfolios with different base currencies).
- Importing/exporting a portfolio between users.
- Cloning a portfolio (creating a new one pre-populated from an existing one).
- Automatic archival policies (e.g. archive after N months of inactivity).
- Audit log of portfolio modifications.

---

## 13. Rationale

The portfolio is modeled as a single-currency container by deliberate choice: this is what makes the financial calculations downstream (FX engine, KPIs) mathematically clean — every figure inside the portfolio resolves to one consistent base, and currency effects are computed at the boundary (purchase lots vs base currency), not in the middle of every KPI.

Soft delete with a separate hard-delete step protects against accidental loss of meaningful historical data (a single misclick should never destroy a year of analysis). At the same time, the existence of a true hard delete avoids forcing users to live with portfolios they truly want gone, and avoids accumulating unrecoverable data the user can no longer reach.

The 10-portfolio default and the global-configuration approach to limits follows the project's broader principle of keeping defaults simple but extensible: the implementer does not need to predict the right number; they only need to make sure the value comes from a single, well-known place.
