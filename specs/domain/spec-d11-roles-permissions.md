# Spec D11 — Roles & Permissions

**Status:** Approved
**Type:** Domain capability
**References:** Spec D01 (Authentication & Identity), Spec D02 (Portfolio Management), Spec D05 (Indicator Catalog & Historical Snapshots), Spec D08 (Internationalization), Spec D10 (Frontend Architecture), Spec 00b (Security Practices), Spec 00e (Prerequisites & Manual Setup), Spec 00f (Global Configuration)

---

## 1. Purpose

Introduce a **role-based access control (RBAC)** system so that every operation in the application is gated by an explicit permission, users hold one or more roles, and roles bundle permissions together.

The system ships with **two roles in v1**:

- **Administrator** — full access to every operation, including user and role management.
- **Investor** — the "typical user" of the application: can manage their own portfolios, assets, lots, sales, price levels, and AI analyses, but cannot manage other users, cannot alter global configuration, and cannot see other users' data.

The design accepts future growth without code changes: adding a third role or reshuffling permissions is a change to the role catalog file, not to application logic.

---

## 2. Conceptual model

Three entities, deliberately kept separate:

1. **Permission** — a single fine-grained atom of authorization. Represents one concrete operation (e.g. `asset.edit_ticker`, `user.list`, `role.assign`). Permissions are the vocabulary in which authorization is expressed everywhere in the codebase.
2. **Role** — a named bundle of permissions (e.g. `administrator`, `investor`). A role is the unit users are granted, not individual permissions.
3. **UserRole** — the link table between users and roles. A user can hold **multiple roles** and their effective permissions are the **union** of the permissions of all their roles.

Reasons for this three-level shape:

- Permissions are granular so the codebase reads clearly (`require_permission("portfolio.delete")` at each endpoint is unambiguous).
- Roles bundle permissions so that users are granted at a level that makes sense in operational language ("this person is an Administrator") rather than as long lists of atoms.
- The user-to-role link is many-to-many because in practice a person is often "an Investor plus something else" (auditor, viewer of a specific project, etc.); v1 does not use this flexibility beyond the two default roles, but the schema does not need to change to support it later.

---

## 3. Catalog storage: seed file + database

The roles and permissions catalog is defined in a versioned seed file at the backend project root: **`roles_catalog.yaml`**.

On application startup:

- The seed file is read.
- Each **permission code** present in the file is upserted into the `permissions` table.
- Each **role code** present in the file is upserted into the `roles` table.
- The relationship between roles and permissions is refreshed to match the file exactly: any `role_permissions` rows in the database that no longer appear in the seed are removed; any new ones are added. This makes the file the single source of truth for "which permissions each role has."
- Any permission or role in the database that is no longer in the seed file is marked `inactive` (not deleted) so that historical audit or debugging remains possible.

Adding a new role or a new permission therefore requires:

1. Editing `roles_catalog.yaml` (add the permission code and its human-readable name; add the role or add the permission to an existing role's list).
2. Editing translation bundles per Spec D08 to add the i18n keys for the new items (only relevant for names shown in the UI — see §7).
3. If the new permission gates a new endpoint that did not exist before, adding the `require_permission("...")` call at that endpoint (part of the normal development of that endpoint, not part of this spec's scope).
4. Restart.

No refactoring of the permission-check logic itself is needed. This is the "data-driven catalog" pattern already established by Spec D05.

---

## 4. Entities

### 4.1 `Permission`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `code` | string | Stable, machine-readable identifier. Unique. Format: `<domain>.<action>` (e.g. `portfolio.create`, `user.list`, `role.assign`, `analysis.upload`). |
| `name_key` | string | i18n key for the human-readable label shown in the UI (e.g. `permission.portfolio.create.name`). |
| `description_key` | string | i18n key for the description shown next to the permission in admin screens. In v1 the resolved value is the same English text regardless of language (same trade-off as D05 §3.2 for indicator descriptions). |
| `active` | boolean | `false` if the permission was in a previous seed but no longer appears in the current one. |
| `created_at`, `updated_at` | timestamp | |

### 4.2 `Role`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key. |
| `code` | string | Stable, machine-readable identifier. Unique. Format: lowercase snake_case (e.g. `administrator`, `investor`). |
| `name_key` | string | i18n key for the display name (e.g. `role.administrator.name`). |
| `description_key` | string | i18n key for the description. |
| `is_default` | boolean | Exactly one role is marked as default per seed file; that role is auto-assigned to newly registered users (see §6.2). |
| `is_admin_role` | boolean | Marks the role that must always have at least one user assigned (bootstrap safety check, §6.1). Exactly one role in the seed has this flag. |
| `active` | boolean | Same semantics as `Permission.active`. |
| `created_at`, `updated_at` | timestamp | |

### 4.3 `RolePermission`

| Field | Type | Notes |
|---|---|---|
| `role_id` | UUID | FK to `roles`. |
| `permission_id` | UUID | FK to `permissions`. |

Composite primary key on `(role_id, permission_id)`. Refreshed atomically on every seed load per §3.

### 4.4 `UserRole`

| Field | Type | Notes |
|---|---|---|
| `user_id` | UUID | FK to `users`. |
| `role_id` | UUID | FK to `roles`. |
| `assigned_at` | timestamp | When the role was granted. |
| `assigned_by_user_id` | UUID, nullable | The administrator who granted the role; null if the assignment was automatic (e.g. registration default). |

Composite primary key on `(user_id, role_id)`. A user's effective permissions are the union of all `RolePermission` entries reachable via their `UserRole` entries.

---

## 5. The v1 catalog

### 5.1 Permissions

The initial permission catalog covers **every operation** in the application. The uniform-coverage decision (§10 rationale) means that no endpoint is "unprotected"; every one requires an explicit permission. This eliminates a class of bugs where a sensitive operation is forgotten in the security review.

Permissions are named `<domain>.<action>` where `<domain>` matches the domain spec that owns the operation:

| Domain | Permission codes (v1) | Owned by spec |
|---|---|---|
| `portfolio` | `portfolio.list`, `portfolio.create`, `portfolio.rename`, `portfolio.archive`, `portfolio.restore`, `portfolio.delete_permanent` | D02 |
| `holding` | `holding.view`, `holding.add_asset`, `holding.delete` | D03 |
| `lot` | `lot.create`, `lot.edit`, `lot.delete` | D03 |
| `sale` | `sale.create`, `sale.edit`, `sale.delete` | D03 |
| `price_level` | `price_level.view`, `price_level.create`, `price_level.edit`, `price_level.delete` | D06 |
| `analysis` | `analysis.upload`, `analysis.view`, `analysis.delete` | D07 |
| `settings` | `settings.view_own`, `settings.edit_own` | (across specs) |
| `user` | `user.list`, `user.view_any`, `user.change_own_password`, `user.change_any_password` | D01 |
| `role` | `role.list`, `role.assign`, `role.revoke` | D11 (this spec) |
| `system` | `system.view_config`, `system.view_audit_log` | 00f |

Every backend endpoint declares which single permission it requires via a decorator or dependency (`require_permission("<code>")`). The **enforcement is at the endpoint level, not in downstream services**, so the check is easy to audit by grepping the codebase for `require_permission`.

Note on **data ownership**: permissions do not override the data-isolation rules already established in each spec. `portfolio.list` allows a user to list portfolios, but per Spec 00b §5 they only see their own. The exception is `user.view_any` and equivalent admin-scope permissions, which grant a role the ability to see across users. This is documented per permission in §5.3.

### 5.2 Roles

Two roles in v1:

**`administrator`** — `is_admin_role: true`, `is_default: false`. Holds **every** permission in the catalog.

**`investor`** — `is_admin_role: false`, `is_default: true`. Holds the permissions typical of a personal portfolio user, applied to their own data:

- All `portfolio.*` (list, create, rename, archive, restore, delete_permanent) — but only over their own portfolios.
- All `holding.*` and `lot.*` and `sale.*` — over holdings within their own portfolios.
- All `price_level.*` — over price levels tied to their own holdings.
- All `analysis.*` — over their own uploaded analyses.
- `settings.view_own`, `settings.edit_own` — their own preferences (language, etc.).
- `user.change_own_password` — password change over their own account.

An investor does **not** hold `user.list`, `user.view_any`, `user.change_any_password`, `role.list`, `role.assign`, `role.revoke`, `system.view_config`, or `system.view_audit_log`. Those are administrator-only.

### 5.3 Scope semantics (own vs any)

Permissions come in two implicit scopes:

- **Own scope** (default): the permission authorizes the operation on data owned by the current user (per Spec 00b §5). This applies to all portfolio, holding, lot, sale, price_level, analysis, and settings permissions.
- **Any scope**: the permission authorizes the operation across all users. Only administrator-level permissions carry this scope: `user.view_any`, `user.change_any_password`, `role.assign`, `role.revoke`, `system.view_config`, `system.view_audit_log`.

There is no separate "own" vs "any" permission code in v1 for non-admin domains; the codebase applies the ownership filter in every service unconditionally. If a future user needs to view another user's portfolios, a new permission (e.g. `portfolio.view_any`) will be added at that time.

---

## 6. Bootstrap: default administrator user

### 6.1 Creation on first startup

At every application startup, the system checks whether at least one user with the role marked `is_admin_role: true` exists in the database. If none is found:

1. The system reads the administrator email from configuration key `security.default_admin_email` (see §11).
2. The system generates a cryptographically random strong password (URL-safe, 24 characters, mixed letters/digits, no ambiguous characters like `0/O` or `1/l`).
3. A `User` is created with:
   - `email` = the configured email.
   - `auth_provider` = `password`.
   - `password_hash` = bcrypt hash of the generated password.
   - `must_change_password` = `true` (new field, see §6.4).
   - The `administrator` role assigned via `UserRole`.
4. The generated password is **printed once** to the standard startup log with a clearly marked banner:

   ```
   =====================================================================
   INITIAL ADMINISTRATOR ACCOUNT CREATED
   ---------------------------------------------------------------------
   Email:    admin@portfolioia.local
   Password: aB7-xK2#pQ9-mR4$vT6-nL8
   ---------------------------------------------------------------------
   This password is shown ONLY at first startup. It will not be shown
   again. The user MUST change it on first login (see must_change_password).
   =====================================================================
   ```

5. If a user with the same email already exists (e.g. someone registered with that email before the admin role was set up), the bootstrap **does not** overwrite or modify them. Instead it aborts with a clear error asking the operator to either change `security.default_admin_email` or assign the administrator role to the existing account manually. This avoids silently altering an existing account.

### 6.2 Default role for new registrations

Whenever a new `User` is created through any of the four registration paths of Spec D01 (Google, Microsoft, password, guest), the system automatically creates a `UserRole` row assigning them the role marked `is_default: true` in the seed (in v1: `investor`). This applies to all four providers uniformly.

The administrator account created at bootstrap (§6.1) is the only exception: it is assigned the `administrator` role directly, and does not receive the default role.

### 6.3 Always-one-admin guarantee

At every startup, after the bootstrap check in §6.1, the system verifies that **at least one active user holds the `is_admin_role` role**. If none does — for example because an administrator revoked the role from the only remaining administrator via the UI (see §7.3), or because a database restoration wiped out the assignment — the startup **fails** with a clear error log. This is deliberate:

- Silently re-creating a new administrator would compromise auditability.
- Continuing to run in a state where no user has admin authority would trap the system in a state that cannot be recovered from the UI.

Recovery in this scenario is a manual DBA action: connect to the database directly and re-insert the `UserRole` link. The failure message includes exactly the SQL fragment needed.

### 6.4 `must_change_password` flag on the User entity

A new field is added to the `User` entity (Spec D01 §5): **`must_change_password`** — boolean, default `false`.

- Set to `true` when the administrator user is auto-created (§6.1).
- Set to `false` when a user successfully changes their password via the "Change password" screen (§7.4).
- Set to `false` also when an administrator resets another user's password (§7.2).

While a user has `must_change_password = true`, the frontend redirects them to the "Change password" screen after login, and every non-password-change API call returns HTTP 428 (Precondition Required) with a body indicating the reason. This ensures the flag cannot be bypassed by navigating to a different screen.

### 6.5 Password change is available to all password-provider users

The "Change password" screen is accessible to every user whose `auth_provider = password`. It is **not** an administrator-only feature. For users whose `auth_provider` is `google`, `microsoft`, or `guest`, the password-change option is displayed in Settings but disabled, with an explanation ("Password change is managed by your identity provider" or "Guest accounts don't have a password").

---

## 7. UI integration

### 7.1 Enforcement pattern (defense in depth)

The frontend applies both layers of the "hybrid" model:

- **Layer 1 (hiding):** the current user's effective permissions are received as part of the login response (see §9) and held in a global signal. Components that render UI elements gated by a permission read from this signal via a helper: `if (hasPermission("portfolio.delete_permanent")) { render delete button }`. If the user lacks the permission, the button, menu item, or entire section is not rendered.
- **Layer 2 (surface a message):** if a user somehow reaches an operation without permission (typed URL, race condition after role revocation, stale UI), the backend rejects the request with HTTP 403 and the frontend displays an inline error message: *"No tienes permisos para esta operación."* (localized per D08).

The backend is the **security boundary**; the frontend hiding is a UX affordance, not a protection. Every backend endpoint enforces its `require_permission` regardless of whether the frontend hid the corresponding UI.

### 7.2 Administrator section

A top-level navigation entry **"Administración"** appears in the app header/sidebar only for users whose effective permissions include any `user.*` or `role.*` permission. This entry expands into a screen with sub-sections:

- **Gestión de usuarios** — list of all users (paginated), showing email, auth_provider, roles, `created_at`, and status. From this list an administrator can:
  - Click a user to see their detail (portfolios count, last login, etc.).
  - Assign or revoke a role (§7.3).
  - Reset another user's password (§7.4). This generates a new random password, sets `must_change_password = true` on that user, and displays the new password once so the administrator can communicate it out-of-band. This is not an email flow (email infrastructure is out of scope for v1).
  - Cannot delete users in v1 (that is a future scope item, §12).

- **Gestión de roles** — read-only in v1. Shows the two roles, their descriptions, and the list of permissions each holds. The catalog file is the source of truth; editing here is out of scope for v1.

Both sub-sections are hidden from users without `user.list` or `role.list` respectively.

### 7.3 Assigning and revoking roles

An administrator viewing another user can toggle any role on or off for that user. The change:

- Creates or deletes a `UserRole` row.
- Records the acting administrator in `assigned_by_user_id` (for grants).
- Rejects the operation if it would leave zero active administrators (§6.3): the system returns HTTP 409 Conflict with a message *"Al menos un usuario debe conservar el rol de Administrador."* This is the runtime enforcement of the guarantee.

An administrator **can** revoke their own admin role, provided at least one other user holds it. This is by design — administrators may want to downgrade themselves for testing. If they are the last one, the system prevents it per the check above.

### 7.4 Change password screen

New screen: **`pi-change-password-screen`** (Screen 12 in the D10 route table).

- Route: `/settings/change-password`.
- Accessible to any authenticated user, regardless of provider. For `google`/`microsoft`/`guest` users, the screen renders an informational message ("this account uses X sign-in; passwords are not managed here") instead of the form.
- For `password` users, the form asks: current password, new password, confirm new password. On successful change, `must_change_password` is set to `false` and the user is redirected to their intended destination (or to the Dashboard).
- If the user has `must_change_password = true`, the "current password" field is skipped (the initial password was just displayed to them; forcing them to re-type it adds no security value and introduces friction). Once they change it, the flag drops.

### 7.5 Permission-denied messaging

When the backend returns HTTP 403 on any endpoint due to a permission miss, the frontend shows a consistent, non-alarming message in the location most natural to the action:

- For form-submit denials: inline near the submit button.
- For navigation attempts (e.g. typing a URL): a full-screen "No tienes permisos para esta operación" placeholder with a link back to the Dashboard.

The message never reveals which permission was required — only that the operation is not authorized. This is a mild information-leakage protection.

---

## 8. Enforcement on the backend

### 8.1 The `require_permission` dependency

Every backend endpoint in FastAPI declares its required permission via a dependency:

```python
@router.post("/portfolios", dependencies=[Depends(require_permission("portfolio.create"))])
def create_portfolio(...): ...
```

The dependency:

1. Reads the authenticated user from the session cookie (per Spec 00b §2 with C01 applied).
2. Loads their effective permissions (union across all their roles). This is cached in-memory per request; there is no per-endpoint database round-trip.
3. Returns 200 OK path or raises HTTP 403 if the permission is missing.
4. On registration or role change during a live session, the next request re-computes the permission set (cached only within a single request).

### 8.2 The "single permission per endpoint" rule

Each endpoint requires **exactly one** permission. Endpoints that require complex authorization (e.g. "the user must own the resource AND have `portfolio.rename`") apply the ownership check in the service layer, not by combining permissions. This keeps `require_permission` simple and auditable.

### 8.3 Missing permission at startup

At startup, the application scans all `require_permission("<code>")` calls and verifies that every referenced code exists in the loaded permission catalog. If any endpoint references an unknown permission, startup **fails** with a clear error listing the endpoint(s) and the missing code(s). This prevents a class of runtime "endpoint always returns 403" bugs where a permission was renamed in the catalog but the code was not updated.

### 8.4 Effective permissions on login

The login response (per Changeset C01 §4) is extended to include the user's effective permissions and their roles:

```json
{
  "user": {
    "id": "uuid",
    "email": "string",
    "display_name": "string | null",
    "preferred_language": "es | en",
    "must_change_password": false,
    "roles": ["investor"],
    "permissions": ["portfolio.list", "portfolio.create", ...]
  },
  "session": {
    "portfolios_count": 0,
    "notifications_poll_interval_seconds": 30
  }
}
```

The `permissions` list is the flat union across the user's roles. It is refreshed on each login; if roles change during a live session, the change takes effect at the user's next login (or after any endpoint calling `/me/refresh-permissions`, added as a helper for the "admin promotes a user, user needs to see the change" case — see §12 out of scope for this endpoint's automated push).

---

## 9. Impact on existing specs (summary)

This spec introduces changes that will be applied to the already-implemented system via **Changeset C02** (a separate document). The impact:

| Spec | Change |
|---|---|
| D01 (Authentication) | `User` gains `must_change_password` field. Login response payload extended to include `roles` and `permissions`. |
| D10 (Frontend) | New screen `pi-change-password-screen`. New screen(s) for Administration section. New helper `hasPermission()` on top of the auth state signal. |
| D08 (i18n) | New translation keys for permission and role names, admin screens, "no permissions" message, password change flow. |
| 00f (Configuration) | New keys under `security.*` (§11). |
| 00e (Prerequisites) | No new environment variables (the admin email is a config value, not a secret). |

The full changelist and acceptance criteria are in Changeset C02.

---

## 10. Rationale

**Why uniform coverage (every operation guarded by a permission).** The alternative — protecting only "sensitive" operations — was considered and rejected. The moment we split the codebase into "operations that check permissions" and "operations that don't", every new endpoint requires a judgment call ("is this sensitive?"), and mistakes accumulate silently. With uniform coverage, the rule is memorable and mechanical: every endpoint declares one `require_permission`, and forgetting is caught at startup by the validator in §8.3. The v1 catalog has ~30 permissions, which is not a significant maintenance cost.

**Why fine-grained permissions rather than functional groups.** Fine-grained permissions read naturally in the codebase (`require_permission("portfolio.delete_permanent")` is self-documenting), and they aggregate cleanly into role definitions. Coarse-grained groups ("manage assets") force the reader to look up what the group means, and force role authors to overprovision when a role needs a subset of the group. The extra file entries are cheap.

**Why seed file over hardcoded.** The rest of the project (D05, D08, 00f) is consistently data-driven; hardcoding roles would have created a lone island of code-driven behavior. The seed file also documents the role definitions in a form that a reader (or a master's thesis reviewer) can inspect at a glance without reading Python.

**Why bootstrap logs the password instead of any alternative.** Fixed defaults (e.g. `changeme`) are indefensible — they end up in documentation and repos and get forgotten. Email delivery requires infrastructure that does not yet exist (Spec D01 §7). Logging is the standard bootstrapping pattern for a reason: whoever runs the first `docker-compose up` sees the logs by construction, and the credential's exposure window is limited to the seconds before first login and the retention of the log itself. Combined with `must_change_password = true`, the initial password's practical lifetime is single-use.

**Why always-one-admin is enforced at startup rather than only at revocation time.** Revocation-time enforcement (§7.3) catches the intentional case, but does not catch a database restoration from a period before the last admin was assigned, nor a data migration bug. The startup check is a cheap safety net that verifies the invariant every time the process comes up.

**Why hybrid enforcement (hide + reject) rather than either alone.** Backend-only enforcement leaks affordances (a user sees a "Delete" button that always returns 403 when clicked, which is confusing). Frontend-only enforcement is trivially bypassed by a direct API call. The combination is standard for any serious web application.

---

## 11. Configuration keys (added to Spec 00f)

New keys added to `config.yaml` via Changeset C02:

| Key | Type | Default | Description |
|---|---|---|---|
| `security.default_admin_email` | string (email format) | `admin@portfolioia.local` | The email of the administrator user auto-created on first startup if no administrator exists. Change this before first startup if you want to receive future email-based flows at your real address. |
| `security.default_admin_password_length` | integer, 16–64 | `24` | Length in characters of the auto-generated initial password. |

---

## 12. Out of scope for v1

- **Editing role definitions from the UI.** The catalog is edited via the seed file only. A read-only "Roles" screen exists for administrators.
- **Creating new roles from the UI.** Same reason.
- **Deleting users** (either via the UI or a self-service "delete my account" flow). The database supports it via cascading deletes but no application-level flow exposes it. This is a GDPR-related item that requires its own care.
- **Fine-grained scope permissions** (e.g. `portfolio.view_any_within_organization`). All admin-scope permissions in v1 are global. Multi-tenant / organization scoping is not a v1 concern.
- **Time-limited role assignments** (e.g. "grant Investor for 30 days"). All assignments are indefinite.
- **Push notification when an administrator changes another user's role.** The change takes effect at the target user's next login (or when they hit a helper `/me/refresh-permissions` endpoint, if implemented). WebSocket-based push is deferred, consistent with other specs' deferral of push infrastructure (D06 §13, D07 §13).
- **Full audit log of every permission-gated action.** A minimal audit trail of role assignments is captured via `UserRole.assigned_at` and `assigned_by_user_id`, but a general-purpose audit log spans multiple domains and merits its own spec.
- **Password reset via email.** Requires email infrastructure not yet in scope (Spec D01 §7).
- **Cross-provider account unification.** A user with `password` and a user with `google` at the same email are separate accounts (Spec D01 §4.2 case 3). Merging is out of scope; roles held by one do not transfer to the other.
