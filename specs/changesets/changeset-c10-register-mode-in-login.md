# Changeset C10 — Add Register Mode to Login Screen (inline toggle)

**Status:** Pending implementation
**Type:** Cross-spec changeset (UX gap fix)
**Triggered by:** User discovered that the login screen has email + password fields for sign-in but no way to register a new email/password account. The backend endpoint `POST /auth/register` exists (per Spec D01 §4 and Changeset C01 §4) but the frontend never exposed it.
**Affects implementations of:** Spec D10, Spec D08

---

## 0. How to read this document

This is a small, focused UX fix — not a spec revision. Spec D01 §4 already defines the four identity sources (Google, Microsoft, password, guest), and Changeset C01 §4 defines the extended `LoginResponse` returned by all four including `/auth/register`. What's missing is the frontend UI to trigger `/auth/register`. C10 fills that gap without changing any contract.

Estimated code impact: ~50 lines of TypeScript + ~5 new translation keys.

---

## 1. Motivation

Current state on the login screen (`pi-login-screen`):
- OAuth buttons: Google, Microsoft ✅
- "Continue as guest" option ✅
- Email + password fields with "Sign in" button ✅
- **Missing:** any way for a new user with email + password to create their account.

The backend endpoint `POST /auth/register` accepts `{email, password, display_name?}` and returns the same `LoginResponse` shape as `POST /auth/login` (per Changeset C01 §4). It also assigns the default role automatically (Changeset C02 §3). So enabling registration on the frontend is purely a UI change — no backend work needed.

---

## 2. Design decisions locked with the project owner

- **UX pattern**: single form with an inline mode toggle. Two links below the fields: *"Iniciar sesión"* (default) and *"Crear cuenta"*. Clicking swaps the form's mode. Compact, mobile-friendly, no route change.
- **Additional field in register mode**: an optional `display_name` field appears when the form is in register mode. In sign-in mode it is hidden.
- **Placeholder for display_name**: `"Ej: Juan Pérez"` (Spanish default per Spec D08).
- **After successful registration**: same behavior as after successful login — the user is logged in immediately (backend returns the session cookie + CSRF cookie), and the router applies the post-login redirect rule from Spec D01 §6 step 8 and Spec D02 §10.
- **No email verification in v1** (consistent with Spec D01 §5 "guest email-only no verification" precedent for the personal-use MVP; the accepted risk is documented in D01).

---

## 3. Implementation — `pi-login-screen` component

### What changes

Extend the existing `pi-login-screen` component with:

1. **A `mode` signal** (`'login' | 'register'`) that determines which mode the form is in. Default: `'login'`.

2. **Two toggle links** below the form buttons:
   - When `mode === 'login'`: show *"¿No tienes cuenta? Crear una"* linking to switch to register.
   - When `mode === 'register'`: show *"¿Ya tienes cuenta? Iniciar sesión"* linking back.

3. **Conditional rendering of the `display_name` field**: visible only when `mode === 'register'`. It is an `<input type="text">`, not required.

4. **Conditional button label**:
   - `mode === 'login'` → button text: *"Iniciar sesión"*.
   - `mode === 'register'` → button text: *"Crear cuenta"*.

5. **Different endpoint on submit** based on mode:
   - `mode === 'login'` → `POST /auth/login` with `{email, password}`.
   - `mode === 'register'` → `POST /auth/register` with `{email, password, display_name}`.
   - `display_name` is included only if the user typed something; if empty, do not send the field (backend will store `null`).

6. **Client-side validation** (same for both modes, per Spec D10 §11):
   - Email: valid format, required.
   - Password: minimum 8 characters, required.
   - Show inline errors under each field on submit if invalid.
   - When switching modes, clear any previous error state so the user doesn't see stale errors.

7. **Reuse the existing error-handling path** for both endpoints: on HTTP 400/422 (validation), show the field-level errors returned by the backend. On HTTP 409 (email already exists on register), show a top-level message: *"Ya existe una cuenta con este email. ¿Quieres iniciar sesión?"* with a link that auto-switches to `login` mode.

### Where in code

- **`frontend/src/screens/login-screen.ts`** — the component. Estimated ~30 additional lines for the mode toggle logic and conditional rendering.
- **`frontend/src/api/auth.ts`** — add a `register(email, password, displayName?)` function that calls `POST /auth/register`. Same return type as `login()` (both return `LoginResponse`).

### Why

The endpoint already exists; the auth flow already accepts the response shape. What's missing is entirely UI. Adding it as a mode toggle instead of a separate route keeps the login-screen file small and the navigation simple — no new route to add to the router table (Spec D10 §6.1).

### Acceptance criteria

- On loading `/login`, the form is in login mode by default.
- Clicking *"Crear una"* switches to register mode: the `display_name` field appears, the submit button says *"Crear cuenta"*, and the bottom link changes.
- Clicking *"Iniciar sesión"* (in register mode) switches back.
- Submitting the login form calls `POST /auth/login`. Submitting the register form calls `POST /auth/register`.
- A successful registration logs the user in and redirects per the standard post-login rule (D02 §10).
- Attempting to register with an existing email shows a clear message and offers to switch to sign-in.
- Attempting to register with an invalid email or password shorter than 8 characters shows inline validation errors before making the API call.

---

## 4. Translations (Spec D08)

Add to `frontend/src/i18n/locales/es.json` and `en.json`:

| Key | Spanish | English |
|---|---|---|
| `login.mode.toggle.to_register` | ¿No tienes cuenta? Crear una | Don't have an account? Sign up |
| `login.mode.toggle.to_login` | ¿Ya tienes cuenta? Iniciar sesión | Already have an account? Sign in |
| `register.submit` | Crear cuenta | Create account |
| `register.display_name.label` | Nombre a mostrar (opcional) | Display name (optional) |
| `register.display_name.placeholder` | Ej: Juan Pérez | E.g. Jane Doe |
| `register.error.email_exists` | Ya existe una cuenta con este email. ¿Quieres iniciar sesión? | An account already exists with this email. Do you want to sign in? |
| `register.error.email_exists.action` | Sí, iniciar sesión | Yes, sign in |

Run the i18n build-time validator introduced in C06 §3 to confirm no keys are missing.

---

## 5. Order of implementation

Single commit is enough. Suggested breakdown:

1. `feat(auth): add register() to auth API client` — the `register` function in `src/api/auth.ts` (~10 lines).
2. `feat(login-screen): add register mode toggle` — the mode signal, conditional rendering, and submit dispatch (~30 lines).
3. `feat(i18n): add register mode translation keys` — the seven new keys in both bundles.

Suggested single-commit alternative: `feat(auth): expose register flow via login screen mode toggle`.

---

## 6. What this changeset does not change

- **Backend**: nothing. Endpoint `POST /auth/register` already exists per Spec D01 §4 and returns `LoginResponse` per Changeset C01 §4.
- **Routing**: no new route added; `/login` handles both modes.
- **Post-login flow**: unchanged. Spec D02 §10 determines the redirect based on `portfolios_count` returned in `LoginResponse`.
- **RBAC**: the newly registered user automatically gets the default role (Investor) per Changeset C02 §3 — no change here.
- **CSRF or cookie handling**: unchanged from C01. The register response sets the same `pi_session` + `pi_csrf` cookies as login.

---

## 7. Out of scope of this changeset

- **Email verification** during registration. Not in v1 (Spec D01 §5).
- **Password strength meter** beyond the minimum-length check.
- **CAPTCHA or bot protection** on the register endpoint. Not needed at MVP scale.
- **Password reset flow** (forgot password). Requires email infrastructure — separate future work.
- **Social account linking** (linking a Google account to an existing password account). Out of scope per D01 §4.2 case 3.
- **Duplicate detection across providers** (e.g. warning if the same email is already used with Google OAuth). Would require additional lookup logic; deferred.

---

## 8. Rationale

The mode-toggle pattern is chosen over a separate `/register` route for three reasons:

1. **Mobile-first design** (Spec D10 §10.4): fewer screen transitions on small viewports keep the flow feeling responsive.
2. **State locality**: the login screen already holds the email/password inputs and the submit handler; reusing them means one component instead of two nearly identical ones.
3. **Discoverability**: users who arrive not knowing whether they have an account already see both options at once, without hunting for a "Register" link elsewhere.

The `display_name` field is kept **optional** because it is not a security concern and forcing it creates friction for users who just want to test the app. If null, the frontend already falls back to displaying the email in headers/menus per Spec D01 §5.
