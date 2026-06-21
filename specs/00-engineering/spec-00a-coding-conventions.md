# Spec 00a — Coding Conventions

**Status:** Approved
**Type:** Cross-cutting engineering spec
**Applies to:** All code, comments, commit messages, and spec documents in this project

---

## 1. Purpose

Establish a single, consistent set of conventions for naming, structure, and language across the entire codebase, so that code generated or guided by specs (Spec Driven Development) is predictable and uniform regardless of which feature it belongs to.

---

## 2. Language policy

- **All code is written in English**: variable names, function names, class names, comments, commit messages, branch names, and log messages.
- **All spec documents are written in English** (this document included).
- **User-facing text is excluded** from this rule — it lives in i18n translation files and may be authored in Spanish first, then translated (see Spec D08 — Internationalization).
- Conversation with the product owner (the developer) may continue in Spanish; this rule applies only to artifacts that become part of the repository.

---

## 3. Python (backend) conventions

| Aspect | Convention |
|---|---|
| Style guide | PEP 8 |
| Formatter / linter | [Ruff](https://docs.astral.sh/ruff/) (replaces Black + Flake8 + isort in a single fast tool) |
| Type hints | Mandatory on all function signatures (parameters and return types) |
| Naming — variables/functions | `snake_case` |
| Naming — classes | `PascalCase` |
| Naming — constants | `UPPER_SNAKE_CASE` |
| Naming — modules/files | `snake_case.py` |
| Naming — private members | prefix with single underscore `_internal_method` |
| Docstrings | Google-style docstrings on all public functions, classes, and modules |
| Line length | 100 characters (Ruff default override) |
| Imports | Absolute imports preferred; grouped as: standard library → third-party → local application (enforced by Ruff) |

**Example:**

```python
def calculate_fx_adjusted_return(
    purchase_price: Decimal,
    current_price: Decimal,
    fx_rate_at_purchase: Decimal,
    fx_rate_current: Decimal,
) -> FxAdjustedReturn:
    """Calculate the return of an asset adjusted for currency exchange effect.

    Args:
        purchase_price: Asset price at purchase, in the asset's quote currency.
        current_price: Current asset price, in the asset's quote currency.
        fx_rate_at_purchase: Exchange rate (quote currency -> base currency) at purchase date.
        fx_rate_current: Current exchange rate (quote currency -> base currency).

    Returns:
        FxAdjustedReturn with asset_return, base_currency_return, and fx_effect.
    """
    ...
```

---

## 4. TypeScript / Frontend conventions

| Aspect | Convention |
|---|---|
| Style guide | Airbnb TypeScript style guide (adapted) |
| Formatter / linter | ESLint + Prettier |
| Naming — variables/functions | `camelCase` |
| Naming — classes/types/interfaces | `PascalCase` |
| Naming — constants | `UPPER_SNAKE_CASE` for true constants, `camelCase` for config objects |
| Naming — files | `kebab-case.ts` for modules, `PascalCase.ts` for component-like files if applicable |
| Type safety | `strict: true` in `tsconfig.json`; no implicit `any` |
| DOM element IDs/data attributes | `kebab-case` |

---

## 5. Database (PostgreSQL) conventions

| Aspect | Convention |
|---|---|
| Table names | `snake_case`, plural (`portfolios`, `purchase_lots`) |
| Column names | `snake_case` |
| Primary keys | `id` (UUID type) |
| Foreign keys | `<singular_table_name>_id` (e.g. `portfolio_id`) |
| Timestamps | `created_at`, `updated_at` (UTC, `timestamptz`) on every table |
| Money / price fields | `NUMERIC` type, never `FLOAT`, to avoid rounding errors in financial calculations |
| Migrations | Managed via Alembic, one migration per logical change |

---

## 6. Git conventions

| Aspect | Convention |
|---|---|
| Commit messages | [Conventional Commits](https://www.conventionalcommits.org/) format: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` |
| Branch naming | `feature/<short-description>`, `fix/<short-description>` |
| Commit language | English |

---

## 7. Spec documents conventions

- Each spec file is named `spec-<number>-<short-name>.md`.
- Each spec has a `Status` field: `Draft`, `Approved`, `Implemented`, `Deprecated`.
- Each spec has a `Type` field: `Domain capability` or `Cross-cutting engineering spec` or `Technical derivation`.
- Domain capability specs are stored under `specs/domain/`.
- Cross-cutting engineering specs are stored under `specs/00-engineering/`.
- Technical derivations (API contracts, data schemas, UI specs) are stored under `specs/technical/`, grouped by the domain spec they derive from.

---

## 8. Rationale

Ruff was chosen over the traditional Black + Flake8 + isort combination because it performs all three roles in a single, significantly faster tool, and has become the de facto standard in modern Python projects as of 2025-2026. This keeps the toolchain simple, which aligns with the project's principle of starting simple and increasing complexity incrementally.
