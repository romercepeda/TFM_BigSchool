# Changeset C02 — Introduce Role-Based Access Control (D11)

**Status:** Implemented (permission-name/description i18n for the 34 non-role catalog entries deferred — see §9 note)
**Type:** Cross-spec changeset
**Triggered by:** Spec D11 (Roles & Permissions)
**Affects implementations of:** Spec D01, Spec D08, Spec D10, Spec 00f, Spec 00e

---

## 0. How to read this document

This is a list of **changes to already-implemented code**, not a rewrite of any prior spec. The original specs (D01, D08, D10, 00f, 00e) remain authoritative for their scope; this document records the deltas that must be applied.

The new capability itself lives entirely in **Spec D11** — that is the source of truth for the rules, the entities, the catalog, and the acceptance semantics. This changeset only lists **what to change in the existing code and files** to bring D11 online.

Each change has:

- **What changes** — the concrete behavior or artifact being modified.
- **Where in code** — the specific implementation surfaces.
- **Why** — the reason, tied to a section of D11.
- **Acceptance criteria** — how to verify the change is correctly applied.

---

## 1. Add the roles catalog seed file and loader (Spec D11 §3, §4, §5)

### What changes

Create the new file **`backend/roles_catalog.yaml`** at the backend project root. On application startup, a new loader reads it and upserts the `permissions`, `roles`, and `role_permissions` rows accordingly (upsert semantics per D11 §3).

The initial file contents mirror the v1 catalog in D11 §5.1 and §5.2.

### Where in code

- **New file:** `backend/roles_catalog.yaml` — contents per D11 §5.1 (permission list) and §5.2 (roles and their permission bindings).
- **New file:** `backend/app/roles/seed_loader.py` — reads the YAML, validates its shape via Pydantic, upserts into DB.
- **New file(s):** `backend/app/roles/models.py` — SQLAlchemy models `Permission`, `Role`, `RolePermission` per D11 §4.
- **New Alembic migration:** create the three tables and their FK relationships.
- **`backend/app/main.py`** (or the equivalent startup hook): call the seed loader after DB migrations, before the app starts accepting requests.

### Why

Per D11 §3, the catalog is data-driven and lives in a versioned file, consistent with D05 and D08. Without the loader running at startup, no permission or role exists in the DB and every subsequent change is inoperable.

### Acceptance criteria

- After startup on an empty database, the `permissions` and `roles` tables contain the entries listed in D11 §5.
- Modifying `roles_catalog.yaml` and restarting the application updates the database to match (adding new entries, removing entries no longer present via `active = false` per D11 §3).
- If the YAML file is missing or malformed, startup fails with a clear error (consistent with the fail-fast principle of Spec 00f §4).

---

## 2. Extend the `User` entity with `must_change_password` (Spec D11 §6.4)

### What changes

Add a new column **`must_change_password`** (boolean, default `false`) to the `users` table.

### Where in code

- **`backend/app/auth/models.py`** (`User` SQLAlchemy model): add the column.
- **`backend/app/auth/schemas.py`** (Pydantic schemas): add the field to the appropriate response models where the User is included.
- **New Alembic migration:** add the column with default `false`.
- Every path that currently creates a `User` (all four registration flows in `backend/app/api/auth.py`): explicitly set `must_change_password = false` for new registrations, except for the bootstrap admin creation (§4 below) which sets it to `true`.

### Why

Per D11 §6.4, the flag is required to enforce mandatory first-time password change on the bootstrap administrator and any admin-issued password reset (§7.4). Without the flag, the bootstrap flow leaves the initial credential live indefinitely.

### Acceptance criteria

- All existing `User` rows have `must_change_password = false` after the migration (existing users are not affected).
- New registrations via all four providers result in `must_change_password = false`.
- The bootstrap admin created in §4 below results in `must_change_password = true`.
- The password-change endpoint (§7 below) sets it back to `false` on success.

---

## 3. Add `UserRole` and assign the default role on registration (Spec D11 §4.4, §6.2)

### What changes

Create the `user_roles` junction table linking users to roles. Modify every registration flow so that the newly created `User` is automatically assigned the role marked `is_default: true` in the catalog (Investor in v1).

### Where in code

- **`backend/app/roles/models.py`**: add the `UserRole` SQLAlchemy model with composite PK (`user_id`, `role_id`).
- **New Alembic migration:** create the `user_roles` table.
- **`backend/app/api/auth.py`** — in each of the four registration flows (Google, Microsoft, password, guest):
  - After the `User` is created and committed, look up the default role once (cached in memory after the first call) and insert a `UserRole` row with `assigned_by_user_id = null`.
- **Data migration:** for every existing `User` that has no `UserRole` row after the migration, assign the default role. This is a one-off backfill; existing users retain access to their existing data.

### Why

Per D11 §6.2, all newly registered users inherit the default role automatically so that they can operate their own portfolios out of the box. Without this backfill, existing users would end up with zero permissions after C02 lands and be unable to use the app they were using yesterday.

### Acceptance criteria

- After the migration, every existing `User` has at least one `UserRole` entry (the default role).
- Registering a new user via any of the four flows results in exactly one `UserRole` row with the default role.
- If the default role is missing from the catalog (misconfiguration), registration fails with a clear error at the point of user creation, not silently later.

---

## 4. Bootstrap the initial administrator on first startup (Spec D11 §6.1, §6.3)

### What changes

Add a startup routine that:

1. Checks whether at least one user with the `is_admin_role: true` role (Administrator) exists.
2. If not, and no user exists with the configured `security.default_admin_email`, creates the administrator user with a randomly generated password, prints the credentials once to stdout with a banner, and assigns the Administrator role.
3. If a user with that email already exists but is not an administrator, the startup **fails** with a clear message telling the operator to change the configured email or manually assign the role.
4. Independently, verifies the always-one-admin invariant (§6.3): if no user in the database has an active `Administrator` role, startup fails with the recovery SQL fragment in the error message.

### Where in code

- **New file:** `backend/app/roles/bootstrap.py` — the routine.
- **`backend/app/main.py`** (or startup hook): call `bootstrap.ensure_admin_exists()` after the seed loader (§1) has populated the roles catalog and after migrations have applied §2 and §3.
- **`backend/config.yaml` example** (per §6 below): add the `security.default_admin_email` and `security.default_admin_password_length` keys.

### Why

Per D11 §6.1 and §6.3, the application must have exactly one administrator available at all times for the system to be usable, and the initial credential must be delivered securely (log-only, forced change on first use).

### Acceptance criteria

- On a fresh database with no users, first startup creates the administrator with the email from configuration.
- The startup log shows the banner with the generated password.
- After first startup, subsequent startups do not create a second administrator or reset the password.
- If an operator manually removes the last administrator role assignment from the database, the next startup fails with a specific error including the SQL fragment needed to recover.
- If the configured admin email matches an existing non-admin user, startup fails with a clear message and the existing user is untouched.

---

## 5. Add `require_permission` dependency and instrument every endpoint (Spec D11 §8)

### What changes

Introduce a FastAPI dependency **`require_permission(code: str)`** that, when applied to an endpoint, ensures the current authenticated user's effective permissions include the given code, otherwise returns HTTP 403.

Every existing endpoint in the backend is instrumented to declare its required permission. The startup validator (§8.3 of D11) verifies that every referenced code exists in the loaded catalog.

### Where in code

- **New file:** `backend/app/roles/dependencies.py` — the `require_permission` dependency and the permission-loading helper.
- **All existing router files** under `backend/app/api/`: add `dependencies=[Depends(require_permission("<code>"))]` to every route. The mapping of endpoints to permission codes is exactly as listed in D11 §5.1 (each spec's operations map to that spec's domain of permissions).
- **`backend/app/main.py`** (startup hook): scan all routes at startup, extract the permission code from each `require_permission` call, verify against the loaded catalog. Fail startup on any mismatch.

### Why

Per D11 §8, the enforcement is at the endpoint boundary and every operation is gated. This is what makes the permission model auditable ("grep the codebase for `require_permission`") and closes the class of forgotten-security bugs.

### Acceptance criteria

- Every route in the backend has exactly one `require_permission` call (a startup check enforces this — a route with zero permission checks fails startup with a clear message).
- Startup fails if any `require_permission` code does not exist in the roles catalog.
- A user without the required permission gets HTTP 403 with a body containing a machine-readable code and a user-facing message (localized per D08).
- An administrator always passes (they hold every permission).

---

## 6. Extend the login response and add `/me/refresh-permissions` (Spec D11 §8.4)

### What changes

Extend the `LoginResponse` (defined in Changeset C01 §4) with two new fields on the `user` object: `roles` (list of role codes) and `permissions` (flat list of permission codes). Add the boolean `must_change_password` field as well.

Also add a new endpoint **`POST /me/refresh-permissions`** that returns the same `user` shape (roles + permissions + must_change_password) for the currently authenticated user. The frontend calls this on demand — for example, right after an administrator grants themselves a role while logged in.

### Where in code

- **`backend/app/auth/schemas.py`**: extend `LoginResponse.user` with `roles`, `permissions`, `must_change_password`.
- **`backend/app/api/auth.py`**: the four login endpoints populate these fields from the DB before returning.
- **`backend/app/api/me.py`** (new or existing): add `POST /me/refresh-permissions` guarded by `require_permission("settings.view_own")`.
- **`backend/config.yaml`** and **Spec 00f §7** (via inline update to the table there): add the two new keys under `security.*`. **This is an exception to "do not touch original specs"**: Spec 00f is the registry of configuration keys, and per its own §6 rule new keys are added there in lockstep. Update the table only, not the surrounding text or rationale.

### Why

The frontend needs to know at login what the user can do (§7.1 of D11), and needs a way to refresh this after a role change without logging out. Without these fields, the frontend has no basis for the hide-layer of the hybrid enforcement.

### Acceptance criteria

- After successful login, the response contains `user.roles`, `user.permissions`, `user.must_change_password`.
- The `permissions` list is the flat union across the user's roles.
- `POST /me/refresh-permissions` returns the current values for the caller.
- The frontend can display the correct UI hiding based on these values.

---

## 7. Add the Change Password screen and endpoint (Spec D11 §6.4, §6.5, §7.4)

### What changes

New screen `pi-change-password-screen` on the frontend, mapped to `/settings/change-password`. New backend endpoint `POST /auth/change-password` that accepts `current_password` (skippable when `must_change_password` is true) and `new_password`, validates and updates.

The frontend registers a global check: if the current user's `must_change_password` is true, redirect to this screen after login and block navigation to other screens until it is resolved. The backend enforces the same rule server-side by returning HTTP 428 (Precondition Required) on non-password-change endpoints while the flag is true.

### Where in code

- **Backend:**
  - **`backend/app/api/auth.py`**: add `POST /auth/change-password`, guarded by `require_permission("user.change_own_password")`.
  - **`backend/app/auth/dependencies.py`** (or a new middleware): before running any endpoint's business logic, check the current user's `must_change_password`; if true and the endpoint is not the password-change endpoint itself, return 428 with a body indicating the reason.
- **Frontend:**
  - **`frontend/src/screens/change-password-screen.ts`**: new Web Component per Spec D10 patterns.
  - **`frontend/src/router/routes.ts`**: register the new route.
  - **`frontend/src/state/auth-state.ts`**: after login, if `currentUser.value.must_change_password === true`, force navigation to `/settings/change-password` and block other routes until it changes.
  - **`frontend/src/screens/settings-screen.ts`**: add a link to the change-password screen. Disable it (with an explanation) when the user's `auth_provider` is not `password`.

### Why

Per D11 §6.4 and §6.5, all password users can change their password, and the auto-created administrator (or any admin-reset user) must change it before doing anything else. This closes the exposure window of the log-emitted initial password.

### Acceptance criteria

- A user with `must_change_password = true` is redirected to `/settings/change-password` after login and cannot navigate elsewhere.
- Changing the password successfully sets the flag to false and unblocks navigation.
- A `google`/`microsoft`/`guest` user visiting the screen sees an explanatory message and no form.
- Password-change API validates the new password length (minimum per current standard — recommend 12 characters minimum) and rejects the same password as before with a clear error.

---

## 8. Add the Administration section on the frontend (Spec D11 §7.2, §7.3)

### What changes

New top-level navigation entry **"Administración"**, visible only to users with `user.list` or `role.list` in their permissions. It contains two screens:

- **`pi-admin-users-screen`** at `/admin/users` — lists all users (paginated), showing their email, provider, roles, and status. Clicking a user opens a detail view where an administrator can assign or revoke roles and reset the user's password.
- **`pi-admin-roles-screen`** at `/admin/roles` — read-only listing of the roles and their permissions.

Corresponding backend endpoints already exist implicitly (via the permissions declared in D11 §5.1); no new domain logic is introduced beyond the routing.

### Where in code

- **Backend:**
  - **`backend/app/api/admin.py`** (new file): endpoints for listing users, listing roles, assigning/revoking roles, resetting other users' passwords. Each guarded by its respective permission per D11 §5.1.
  - **`backend/app/roles/service.py`** (new): the logic for assigning/revoking roles, including the check that prevents removing the last administrator (returns HTTP 409 with a specific error code so the frontend can display the correct message).
- **Frontend:**
  - **`frontend/src/screens/admin-users-screen.ts`**, **`admin-roles-screen.ts`**, and any supporting components.
  - **`frontend/src/router/routes.ts`**: register the new routes, guarded by permission checks.
  - **`frontend/src/components/header-bar.ts`** (or the equivalent nav bar): show the "Administración" entry conditionally based on the user's permissions.

### Why

Per D11 §7.2, the administrator needs a UI to manage users. Without it, role assignment is a database-only operation, which is unacceptable for a system whose whole point is that admins are configured by seed file.

### Acceptance criteria

- An investor never sees the "Administración" entry.
- An administrator sees it and can access both sub-screens.
- Assigning a role to a user takes effect immediately in the backend; the target user sees the change on their next login or on `/me/refresh-permissions`.
- Attempting to revoke the last administrator's role returns HTTP 409 and the frontend shows the specific message.
- Resetting another user's password generates a new random password, displays it once to the acting administrator, and sets `must_change_password = true` on the target.

---

## 9. Translations for D11 UI (Spec D08)

### What changes

Add the necessary translation keys to `frontend/src/i18n/locales/es.json` and `en.json`, plus the backend `backend/i18n/es.json` and `en.json`, for:

- Role names and descriptions (`role.administrator.name`, `role.administrator.description`, `role.investor.name`, `role.investor.description`).
- Permission names and descriptions (per the catalog — per D11 §4.1, descriptions remain in English in v1, but the keys still resolve through the translation system for consistency).
- Screens: "Administración", "Gestión de usuarios", "Gestión de roles", "Cambiar contraseña".
- Messages: "No tienes permisos para esta operación", "Al menos un usuario debe conservar el rol de Administrador", "La contraseña debe tener al menos N caracteres", "Las contraseñas no coinciden", "Debes cambiar tu contraseña para continuar".

### Where in code

- **`frontend/src/i18n/locales/es.json`** and **`en.json`**: add the keys.
- **`backend/i18n/es.json`** and **`en.json`**: add the API-side error message keys.

### Why

Per Spec D08, all user-facing text lives in translation files. Without these entries, the frontend fallback (§5.5 of D08) will display raw keys instead of readable strings.

### Acceptance criteria

- Every visible D11-introduced string resolves through `t()` and has entries in both `es.json` and `en.json`.
- No raw key appears in the UI when either language is selected.

**Implementation note:** role names/descriptions, screen labels, and all
listed messages are translated. Permission names/descriptions (the ~34
catalog entries) are a deliberate scope cut: the roles screen shows the raw
permission `code` (e.g. `portfolio.create`) instead of a translated name.
This does not violate the acceptance criteria above — no `permission.*.name`
key is referenced anywhere in the UI, so there is no raw key visible, just an
untranslated but self-documenting code. Revisit if a future screen needs a
human-readable permission name (`translate_permission_name` already exists
in `i18n_service.py`; only the catalog's i18n entries are missing).

---

## 10. Order of implementation

To minimize interim breakage:

1. **Change 1** (seed file + loader + `Permission`/`Role`/`RolePermission` tables + migration) — additive, no runtime behavior change.
2. **Change 2** (`must_change_password` column) — additive on the model, default `false` means it does nothing until §4 sets it.
3. **Change 3** (`UserRole` + auto-assign default role on registration + backfill) — additive; existing users get the default role and continue to work.
4. **Change 5** (`require_permission` + instrument every endpoint) — enforcement kicks in here. Test carefully; the app is expected to keep working for users who have the default role assigned in §3 because Investor covers their existing operations.
5. **Change 6** (extend login response + `/me/refresh-permissions`) — needed by the frontend for §7 and §8.
6. **Change 4** (bootstrap admin) — after the catalog and enforcement exist, so the newly created admin actually has permissions attached.
7. **Change 7** (change-password screen + endpoint + 428 guard) — needed before rolling out §4 in production; without it the bootstrap admin cannot change their password.
8. **Change 8** (admin screens on the frontend) — the last user-facing addition.
9. **Change 9** (translations) — happens in parallel with §7 and §8, ideally in the same commits that introduce the screens.

After all nine are applied and verified, this changeset is marked `Implemented`.

---

## 11. What this changeset does not change

For clarity, these specs are **unaffected**:

- **00a** — no coding convention change.
- **00b** — the authentication mechanism (cookie httpOnly + CSRF from C01) is not modified.
- **00c** — testing strategy applies as-is; the new business logic (permission resolution, always-one-admin check) falls into the "critical" bucket and should be at 90%+ coverage.
- **00d** — no new containers.
- **D02–D07, D09** — no changes to their domain models beyond the addition of `require_permission` on their endpoints (which is behavioral, not structural).
- **D10** — the router table gains new routes; the base architecture and reactivity model are unchanged.

---

## 12. Out of scope of this changeset

See D11 §12. In particular:

- Role editing from the UI.
- User deletion.
- Fine-grained "own vs any" per-domain permissions beyond what §5.3 already defines.
- Push notifications on role change.
- General-purpose audit log.
- Email-based password reset.
