# Changeset C01 — Backend adjustments for Frontend integration (D10)

**Status:** Pending implementation
**Type:** Cross-spec changeset
**Triggered by:** Spec D10 (Frontend Architecture & Components)
**Affects implementations of:** Spec 00b, Spec 00c, Spec 00e, Spec D01, Spec D07

---

## 0. How to read this document

This is **not** a new spec. It is a **list of changes** to the already-implemented parts of the system, made necessary by the addition of Spec D10. The original specs (00b, 00c, 00e, D01, D07) **remain authoritative as-is**; this document records the deltas that must be applied to their implementations.

When you (or an AI assistant) implement these changes, do **not** rewrite the original specs. Each change below has:

- **What changes** — the concrete behavior or text being modified.
- **Where in code** — the implementation surface(s) that need updating.
- **Why** — the reason, tied to a section of D10.

After all changes are applied and verified, this changeset is marked `Implemented` and archived in `specs/changesets/`. A second version (`C02`) would be a new file, never overwrite this one.

---

## 1. Authentication transport model (Spec 00b §2)

### What changes

The session token transport changes from **"access token + refresh token, refresh in httpOnly cookie"** to **"single JWT session token in httpOnly cookie, sent automatically with every request via browser-managed cookies"**. The frontend does **not** read or set tokens; it only sets `credentials: 'include'` on every HTTP call.

New requirements introduced by this model:

1. **Cookie attributes**: the session cookie must be set with `HttpOnly`, `Secure` (when served over HTTPS), `SameSite=Lax` (or `Strict` if all flows allow), `Path=/`.
2. **Token lifetime**: a single session token with configurable lifetime. Suggested default: **7 days** for the personal-use MVP. The access-vs-refresh split is **out of scope for v1**.
3. **CSRF protection**: because cookies are sent automatically, the backend implements the **double-submit cookie pattern** on every state-changing endpoint (`POST`, `PUT`, `PATCH`, `DELETE`):
   - Issue a separate, non-httpOnly cookie (e.g. `csrf_token`) at login. Its value is a random token tied to the session.
   - The frontend reads this cookie via `document.cookie`, and sends its value in a custom request header (e.g. `X-CSRF-Token`) on every state-changing call.
   - The backend rejects requests whose header value does not match the cookie value, with HTTP 403.
   - Read-only requests (`GET`, `HEAD`, `OPTIONS`) are exempt.

### Where in code

- **Backend**, authentication routes (login endpoints for all four providers, logout endpoint): set the session cookie with the attributes above. Issue the CSRF cookie alongside.
- **Backend**, FastAPI middleware: add CSRF validation middleware that runs before route handlers for state-changing methods. Skips `GET`/`HEAD`/`OPTIONS`.
- **Backend**, OAuth flows (Authlib integration): after exchanging the OAuth code for the third-party token and creating/finding the User, set the session cookie and the CSRF cookie in the redirect response.
- **Frontend** (Spec D10 implementation): the API client wrapper at `src/api/client.ts` must:
  - Set `credentials: 'include'` on every `fetch`.
  - Before any state-changing request, read the CSRF cookie value via `document.cookie` and add it as an `X-CSRF-Token` header.

### Why

Per D10 §7.1, the frontend is built on Web Components and uses cookie-based authentication via `credentials: 'include'`. The original 00b spec described a hybrid model (access + refresh) that does not match the frontend's actual implementation pattern. Unifying both around a single cookie-based session token is more secure against XSS (no JS-accessible tokens at all) and simpler to implement at this MVP scale.

### Acceptance criteria

- A user who logs in receives an `HttpOnly` cookie with the JWT, and a separate non-httpOnly cookie with a CSRF token.
- A `POST /portfolios` request without an `X-CSRF-Token` header (or with a wrong value) returns HTTP 403, regardless of whether the session cookie is valid.
- A `GET /portfolios` request without an `X-CSRF-Token` header succeeds normally.
- Logout clears both cookies.
- After 7 days of inactivity, the session cookie expires and the user is forced to re-authenticate.

---

## 2. Frontend environment variable naming (Spec 00e §6)

### What changes

Any environment variable that must be readable by the **frontend** (the compiled JavaScript that runs in the browser) needs the `VITE_` prefix. Otherwise Vite does not embed the value into the client bundle (this is a security feature of Vite — variables without `VITE_` are visible to the build process but not to the shipped client code).

The variable currently named `BACKEND_BASE_URL` in 00e §6 is used by the frontend to know where to send API calls. It must be renamed (for frontend purposes) to `VITE_BACKEND_BASE_URL`.

The variables in 00e §6 are reorganized into two groups:

**Backend-only** (read by the FastAPI process, no prefix required):
- `JWT_SIGNING_KEY`, `DATABASE_URL`, `REDIS_URL`, `GOOGLE_OAUTH_*`, `MICROSOFT_OAUTH_*`, `MARKET_DATA_*`, `AI_*`, `FRONTEND_BASE_URL` (used by the backend for OAuth redirects and CORS), `BACKEND_BASE_URL` (used by the backend for self-referential URLs like OAuth callback URLs).

**Frontend-only** (read by Vite-compiled client code, `VITE_` prefix required):
- `VITE_BACKEND_BASE_URL` — the URL the browser uses to reach the API. **In development this typically equals the value of `BACKEND_BASE_URL`** (both point at `http://localhost:8000`), but they are conceptually distinct and may diverge in production (e.g. if the backend is reachable on a different hostname from inside the cluster vs from the public internet).

### Where in code

- **`.env` file** at the project root (local development): add `VITE_BACKEND_BASE_URL` alongside the existing `BACKEND_BASE_URL`. They will usually hold the same value in development.
- **`.env.example`**: same update, with placeholder values.
- **`docker-compose.yml`**: pass `VITE_BACKEND_BASE_URL` to the `frontend` build stage (build-arg or environment variable, depending on how the Dockerfile is structured).
- **`frontend/Dockerfile`**: ensure `VITE_BACKEND_BASE_URL` is available during `npm run build` (Vite reads it at build time, not runtime).
- **Deployment scripts / Azure config**: ensure the `VITE_BACKEND_BASE_URL` variable is set in the build pipeline for production deploys; the backend's own `BACKEND_BASE_URL` is set on the backend service.

### Why

Per D10 §7.1 and §14, the frontend is bundled with Vite. Vite's contract is that only environment variables prefixed with `VITE_` are exposed to client code via `import.meta.env`. The original 00e spec was written before D10 settled on Vite, so it used a generic `BACKEND_BASE_URL` name. Without this rename, the frontend build would not see the variable and the resulting client bundle would have `import.meta.env.VITE_BACKEND_BASE_URL === undefined`, causing all API calls to break.

### Acceptance criteria

- `.env` and `.env.example` contain `VITE_BACKEND_BASE_URL`.
- A built frontend bundle, when inspected, contains the value of `VITE_BACKEND_BASE_URL` embedded in the JavaScript (no longer `undefined`).
- `BACKEND_BASE_URL` (without the prefix) remains available to the backend process for OAuth callback URL construction.

---

## 3. Testing framework selection (Spec 00c §2)

### What changes

Spec 00c originally offered "Vitest **or** Jest" without making a choice. D10 §2 selects Vitest definitively. The implementation should:

- Use **Vitest** as the frontend test runner.
- Use **`@open-wc/testing`** as the helper library for Web Component tests (mounting components in a test environment, querying their shadow root, dispatching events).

Jest is no longer a consideration.

### Where in code

- **`frontend/package.json`**: `vitest` and `@open-wc/testing` as devDependencies.
- **`frontend/vitest.config.ts`**: Vitest configuration, integrated with the Vite config.
- **`frontend/tests/`**: test files follow Vitest's discovery conventions (`*.test.ts` or `*.spec.ts`).
- **CI pipeline** (when added, currently manual per Spec 00d §5): `npm run test` invokes Vitest.

### Why

D10 §2 and §12 settle the testing choice. Leaving 00c as "Vitest or Jest" creates ambiguity that costs implementer time later. This is purely a clarification, not a change of strategy — Vitest was already the preferred option per Spec 00c §3.

### Acceptance criteria

- `npm run test` in the `frontend` directory runs Vitest.
- At least one example component test exists using `@open-wc/testing`, demonstrating the pattern for future tests.

---

## 4. Login response payload (Spec D01 §6 and Spec D07 §10)

### What changes

The response of a successful login (any of the four providers) is extended to include configuration the frontend needs to operate immediately, so it does not require a second roundtrip:

- The user's `id`, `email`, `display_name`, `preferred_language` (already implicit per D01 §5).
- The number of active portfolios the user owns (`portfolios_count`), so the frontend can apply the post-login routing rule (D02 §10) without an extra call.
- The notification polling interval (`notifications_poll_interval_seconds`), so the frontend's header-bar component (D07 §10) knows how often to poll without hardcoding a value.

The login response shape becomes:

```json
{
  "user": {
    "id": "uuid",
    "email": "string",
    "display_name": "string | null",
    "preferred_language": "es | en"
  },
  "session": {
    "portfolios_count": 0,
    "notifications_poll_interval_seconds": 30
  }
}
```

Note that the session token itself is **not** in the response body — it travels in the httpOnly cookie set by the response headers (per Section 1 of this changeset).

### Where in code

- **Backend**, all four login endpoints: extend the response model to include the `session` object with `portfolios_count` (computed from the user's active portfolios) and `notifications_poll_interval_seconds` (from `ai.notifications.poll_interval_seconds` in `config.yaml`).
- **Backend**, Pydantic response model for login: define `LoginResponse` with `user` and `session` sub-models.
- **Frontend** (Spec D10 implementation): the auth API module at `src/api/auth.ts` consumes this shape. The router (`src/router/router.ts`) reads `portfolios_count` to decide where to redirect. The header-bar component (`src/components/header-bar.ts`) reads `notifications_poll_interval_seconds` to configure its polling interval.

### Why

D10 §6.3 requires the post-login redirect logic to know how many portfolios the user has, and D10 §8 requires the polling interval. Without exposing these in the login response, the frontend would need to make a `GET /me/portfolios` call right after login (for the count) and a separate config call (for the interval), adding latency and complexity. Returning them in the login response is the natural, single-roundtrip pattern.

### Acceptance criteria

- The login response of any provider includes the `session.portfolios_count` field.
- The login response of any provider includes the `session.notifications_poll_interval_seconds` field, with the value from `config.yaml`.
- The frontend uses these values directly without making a follow-up API call.

---

## 5. Order of implementation

If implementing these changes incrementally, the order that minimizes interim breakage is:

1. **Change 2** (environment variable rename) — only adds a new variable; the old one keeps working temporarily.
2. **Change 3** (testing framework) — purely additive.
3. **Change 4** (login response payload) — additive on the backend; the frontend can read the new fields when ready.
4. **Change 1** (authentication transport) — most invasive; touches login flow, every state-changing endpoint, and the frontend API client. Implement and test in a feature branch.

---

## 6. What this changeset does **not** change

For clarity, these specs are **unaffected** and require no implementation changes:

- **00a** Coding conventions.
- **00c** Testing strategy (except for §3 below — only clarifies the choice, the strategy itself stays).
- **00d** Containerization (the Nginx-served frontend, the Redis container, the Postgres container — all unchanged).
- **00f** Global configuration (no new keys introduced).
- **D02–D06**, **D08**, **D09** — no entity-level or behavioral changes.

---

## 7. Out of scope of this changeset

These items were noted during the D10 audit but are deliberately **not** part of this changeset:

- **Automatic OpenAPI type generation** between backend and frontend (Pydantic → TypeScript types). Manual sync remains the v1 mechanism per D10 §13.
- **End-to-end browser testing** (Playwright, Cypress). Remains out of scope per Spec 00c §5 and D10 §15.
- **Service Worker / PWA support**. Remains out of scope per D10 §15.
