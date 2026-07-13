# Spec 00c — Testing Strategy

**Status:** Approved
**Type:** Cross-cutting engineering spec
**Applies to:** Backend (primary), Frontend (secondary)

---

## 1. Purpose

Define what is tested, how, and to what coverage target, so that testing effort is concentrated where it protects the system most — financial calculations and business rules — rather than spread uniformly across trivial code.

---

## 2. Testing scope

| Layer | Test type | Tooling | Priority |
|---|---|---|---|
| Business logic (FX engine, indicator evaluation, alert engine, price-level engine) | Unit tests | `pytest` | **Critical** |
| API endpoints (FastAPI routers) | Integration tests | `pytest` + FastAPI `TestClient` | High |
| Database layer (repositories) | Integration tests against a test database | `pytest` + test PostgreSQL instance (or SQLite in-memory for fast feedback, where compatible) | Medium |
| Frontend (TypeScript) | Unit tests on pure logic/utility functions only | `Vitest` or `Jest` | Low (orientation only, not a hard target) |
| Frontend UI rendering | Manual / exploratory testing | — | Not automated in v1 |

---

## 3. Coverage targets

- **80% line/branch coverage** on backend business logic modules (FX calculation, indicator evaluation, alert detection, price-level tracking). This is the figure reportable as evidence to the master's program evaluators.
- **90-100%** is the aspirational target specifically for the FX calculation engine and indicator threshold evaluation, since errors there directly produce incorrect financial figures shown to the user.
- API router/integration layer: covered by integration tests for the main success path and key error cases (validation errors, not-found, unauthorized) — no fixed % target, judged by scenario completeness instead.
- Frontend: no enforced %; tests are written for pure calculation/formatting utilities only (e.g. currency formatting, percentage display), not for UI rendering.

Coverage is measured with `pytest-cov` and reported as part of the CI pipeline (or, in the absence of CI in early MVP stages, run manually before each milestone and recorded in the spec status).

---

## 4. Test data conventions

- Tests use fixtures with realistic but clearly fictional data (no real tickers tied to real personal portfolios).
- Currency conversion tests must include at least one scenario where the exchange rate moves favorably and one where it moves unfavorably, to validate both directions of the FX effect calculation.
- Indicator evaluation tests must include one case per threshold zone (positive / neutral / attention) per indicator.

---

## 5. What is explicitly out of scope for v1

- An automated, CI-run end-to-end browser test suite (e.g. Playwright/Cypress as a checked-in `*.spec.ts` suite gating merges) — deferred to a later iteration once the UI stabilizes. This is distinct from Section 7's AI-driven manual verification, which is in scope and mandatory today.
- Load/performance testing — deferred until the system has real concurrent usage to model.
- Mutation testing — not required for the MVP.

---

## 6. Rationale

A flat coverage percentage across the whole codebase is a weak signal: it can be satisfied by testing trivial getters while leaving critical financial math unverified. This spec instead ties the 80% target specifically to business logic, and treats thinner layers (routers, frontend rendering) with lighter, scenario-based testing. This approach is defensible in an academic evaluation because it demonstrates testing effort is risk-driven, not just metric-driven.

---

## 7. AI-assisted manual verification with Playwright (Changeset C18)

Every non-trivial change — including backend-only changes that surface in the UI — is driven and screenshotted with Playwright before being considered done, using an AI coding session (not a checked-in automated test suite; see Section 5's distinction). This replaced ad-hoc, session-specific verification approaches (manually crafted JWTs, guessed credentials, one-off scripts) with one documented, repeatable procedure.

The full how-to — starting services, the login flow and its in-memory-auth-state gotcha, route shapes, the standing `playwright@verify.com` verification account and how to reprovision it, shadow-DOM selector behavior, and the screenshot folder convention — lives in **`.claude/skills/verify-playwright/SKILL.md`**, not duplicated here, so it stays a single source of truth that a session actually reads before acting (a spec is consulted for *what/why*; the skill is consulted for *how*, same split as `scripts/db.ps1` vs. Spec 00a's migration discipline).

Screenshots are saved under `verification-screenshots/<changeset-or-spec-slug>/`, gitignored — they are working evidence for the session and for Romer's review, not repo content to commit.
