# Spec D01 — Authentication & Identity

**Status:** Approved
**Type:** Domain capability
**References:** Spec 00b (Security Practices)

---

## 1. Purpose

Allow a person to access the system and have their portfolios, assets, and analyses persistently associated with their identity, through any of four supported identity sources, with minimal friction for the most casual use case (guest).

---

## 2. Supported identity sources

| Source | Identifier | Password required | Configuration toggle | Notes |
|---|---|---|---|---|
| Google | Email (from Google account) | No (OAuth) | `authentication.methods.google.enabled` | Standard OAuth 2.0 flow via Authlib |
| Microsoft | Email (from Microsoft account) | No (OAuth) | `authentication.methods.microsoft.enabled` | Standard OAuth 2.0 flow via Authlib, using Azure Entra ID app registration |
| Email + Password | Email | Yes | `authentication.methods.password.enabled` | Traditional registration; password hashed per Spec 00b |
| Guest | Email only | No | `authentication.methods.guest.enabled` | No password, no OAuth — see Section 4 |

All four sources produce the same internal `User` entity; the system does not treat guest users as a structurally different type of account, only as one with a different authentication method.

Each source can be independently enabled or disabled via the global configuration file (see Spec 00f, Section 7.3). When a source is disabled: its login option is hidden from the UI, the corresponding backend endpoint rejects requests, and existing users with that `auth_provider` are temporarily blocked from logging in (no data deletion or modification) until the source is re-enabled. By default in v1, all four sources are enabled.

---

## 3. OAuth implementation approach

- Implemented directly with **Authlib** against Google's and Microsoft's standard OAuth 2.0 / OpenID Connect endpoints.
- No third-party identity platform (Auth0, Firebase Auth, Azure AD B2C) is used, to avoid recurring cost and to keep the system portable across hosting providers — this was an explicit decision (see conversation record / Spec 00b rationale).
- Cost: Google and Microsoft OAuth app registration is free with no usage limits relevant to this project's scale.
- Required setup (not part of this spec, but noted for implementation): a registered OAuth application in Google Cloud Console and in Azure Entra ID, each providing a client ID and client secret, stored as environment variables per Spec 00b.

---

## 4. Guest accounts

- A guest account is created or re-accessed by providing **only an email address** — no password, no third-party login, no additional verification.
- Guest accounts **persist indefinitely**; there is no automatic expiration.
- **A guest account cannot be created for an email that already exists** as a non-guest account (`auth_provider` in `password`, `google`, or `microsoft`). See Section 4.2.
- **Re-entry behavior (existing guest):**
  1. User enters an email on the "Continue as guest" flow.
  2. The system looks up an existing `User` with `auth_provider = guest` and that exact email.
  3. **If found:** the system logs the user into that existing account, loading their existing portfolios and configuration. No further verification is performed.
  4. **If not found** (and no non-guest account exists with that email either): the system creates a new `User` with `auth_provider = guest` and that email, and proceeds as a brand-new user.

### 4.1 Migration from guest to a registered account

When a user registers for the first time with `password`, `google`, or `microsoft` using an email that **already exists as a guest account**, the system offers to migrate the data from the guest account to the new registered account.

**Trigger:** detected during initial account creation only — not on subsequent logins.

**User prompt:** the system displays a confirmation message:
> *"A guest account exists for this email. Do you want to inherit its data (portfolios, assets, lots, analyses) into your new account?"*
>
> Options: **Yes, inherit data** / **No, start with a clean account**.

**If user chooses "Yes, inherit data":**
1. All entities owned by the guest `User` (portfolios, assets, lots, price levels, analyses, settings, etc.) are reassigned atomically to the new registered `User`.
2. The new registered `User` is created with `auth_provider` set to the new registration method (`password`, `google`, or `microsoft`) — **not** `guest`. The `auth_provider` field always reflects the current authentication method of the account; it is never `guest` after a successful migration.
3. The guest `User` record is **hard-deleted** from the database. No trace of the previous guest account is preserved.
4. The migration must occur within a single database transaction. If any step fails, the entire migration is rolled back and the new account is not created (the user is informed and may retry).

**If user chooses "No, start with a clean account":**
1. The new registered account is created empty.
2. The guest account with the same email is **also deleted**, because per Section 4 a guest account cannot coexist with a non-guest account on the same email. The user is informed before confirmation that proceeding without inheriting will result in the loss of the previous guest data.

**Same rules apply to all three non-guest providers** (`password`, `google`, `microsoft`): the migration prompt is shown whenever a new registered account is created with an email that matches an existing guest account.

### 4.2 Conflict cases

| Scenario | Behavior |
|---|---|
| User tries to "Continue as guest" with an email that already exists as a non-guest account (`password`, `google`, or `microsoft`) | System displays error: *"An account already exists with this email. Please sign in using the corresponding method."* No guest account is created. |
| User tries to register with `password` using an email that already exists as `password` | Standard "email already in use" error — handled as in any registration flow, not a migration case. |
| User tries to register with `google` or `microsoft` and the OAuth flow returns an email that already exists as a non-guest account with a *different* provider | Out of scope for v1. Documented as a known limitation: the system will treat the second registration attempt as an error. Cross-provider unification is deferred. |
| User has a guest account and registers with `password`, `google`, or `microsoft` using the same email | Migration prompt is shown (Section 4.1). |

### 4.3 Accepted security risks (explicit, documented, intentional)

Because no verification is required to access or migrate a guest account by email alone, **two risks are knowingly accepted for v1:**

1. **Account read access by email:** anyone who knows or guesses a guest user's email can sign in as that guest and view their financial data.
2. **Guest account hijacking via migration:** anyone who registers with `password`, `google`, or `microsoft` using a known guest email can, by accepting the migration prompt, take ownership of the guest's data and cause the original guest account to be deleted.

These risks are **deliberate v1 scope decisions** based on personal-use targeting, and must **not** be treated as oversights by whoever implements this spec. Mitigating them (e.g. magic-link email verification before guest access, or before migration) is deferred to a future iteration and is **not** part of v1.

---

## 5. User entity (conceptual)

| Field | Description |
|---|---|
| `id` | Internal unique identifier (UUID) |
| `email` | Used as the identifying field across all four sources |
| `auth_provider` | `google` \| `microsoft` \| `password` \| `guest` |
| `password_hash` | Present only when `auth_provider = password`; null otherwise |
| `display_name` | Optional, populated from OAuth profile when available |
| `preferred_language` | For the i18n system (see Spec D08 — Internationalization) |
| `created_at` | Timestamp |

A user owns one or more Portfolios (see Spec D02 — Portfolio Management), each with its own base currency.

---

## 6. Functional flow

1. User opens the application and reaches the Login screen (UI Screen 1, as defined in the functional design).
2. User chooses: "Continue with Google", "Continue with Microsoft", "Email + Password", or "Continue as guest".
3. **Google/Microsoft (new registration):** redirected to the provider's consent screen; on success, the system checks whether a guest account exists with the returned email:
   - If yes → migration prompt is shown (Section 4.1) before the new `User` is finalized.
   - If no → new `User` is created directly; session token issued.
4. **Google/Microsoft (returning user):** system matches the existing `User` by email and provider; session token issued.
5. **Email + Password (new user):** user provides email and password. System checks whether a guest account exists with that email:
   - If yes → migration prompt is shown (Section 4.1) before the new `User` is finalized.
   - If no → password is hashed and stored; session token issued.
6. **Email + Password (returning user):** credentials validated against the stored hash; session token issued on match.
7. **Guest:** user provides only an email. Per Section 4 lookup logic:
   - If a guest account exists with that email → log into it directly (existing portfolios loaded, no verification).
   - If a non-guest account exists with that email → reject with error "An account already exists with this email. Please sign in using the corresponding method." (Section 4.2).
   - Otherwise → create a new guest `User` and proceed as a new user.
   Session token issued where applicable. No verification email is sent in v1.
8. On successful authentication (any source), the user is routed to "My Portfolios" if they have more than one portfolio, directly to the Dashboard if they have exactly one, or to "Create Portfolio" if they have none yet.

---

## 7. Out of scope for v1

- Cross-provider account unification (a user with `password` on email X is treated as a separate account from one with `google` on email X — see Section 4.2).
- Password recovery flow details (deferred to a follow-up technical spec once email-sending infrastructure is decided).
- Multi-factor authentication.
- Email verification (no magic links, no confirmation emails — see Section 4.3 for the accepted risks).
- Account deletion / GDPR-style data export (to be addressed before any public/multi-user release, not required for personal MVP use).

---

## 8. Rationale

The four-source model prioritizes minimal friction (guest, one field) while still supporting standard secure login (Google, Microsoft, password) for a user who wants persistence guarantees beyond "don't lose your session token."

Guest-to-registered migration **is supported in v1** because losing accumulated data when registering would be a poor experience for a personal-use product. To keep this manageable in scope: migration is one-shot (only at first registration, not on every login), explicitly confirmed by the user (no silent data movements), and atomic (a single transaction). The companion rule that no guest account can be created on an email that already has a non-guest account closes the door on duplicate-email situations going forward.

The trade-offs — guest accounts are accessible to anyone who knows the email, and a malicious actor who knows a guest's email can hijack their data through the migration flow — are accepted knowingly because the system targets personal/single-user use in v1. They are documented in Section 4.3 precisely so they are never mistaken for implementation bugs.
