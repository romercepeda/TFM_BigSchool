# Spec 00b — Security Practices

**Status:** Approved
**Type:** Cross-cutting engineering spec
**Applies to:** Backend, frontend, database, deployment

---

## 1. Purpose

Define the baseline security practices that apply across the whole system, independent of any single feature. This spec is referenced by domain specs whenever they touch authentication, personal data, financial data, or external integrations.

---

## 2. Authentication & session management

- Authentication supports four identity sources: Google OAuth 2.0, Microsoft OAuth 2.0 (Azure Entra ID), email + password, and guest (email-only, no password).
- OAuth is implemented directly using **Authlib**, with no third-party identity-as-a-service dependency, to keep the system portable across hosting providers (see Spec — Authentication, domain capability).
- Passwords (email + password accounts) are hashed using **bcrypt** (or Argon2 if available in the chosen library), never stored in plain text, never logged.
- Session tokens are **JWT**, signed with a secret stored as an environment variable (never committed to the repository).
- Access tokens are short-lived (suggested: 15-30 minutes); refresh tokens are longer-lived and stored securely (httpOnly cookie, not accessible via JavaScript).
- Guest accounts (email-only) do not have a password and are not eligible for password-based login; their session relies solely on the issued token.

---

## 3. Secrets management

- No secret (API keys, database credentials, JWT signing key, OAuth client secrets) is ever committed to the repository.
- All secrets are read from environment variables, loaded via a `.env` file in local development (excluded via `.gitignore`) and via the cloud provider's secret manager in production (e.g. Azure Key Vault, if deployed on Azure).
- A `.env.example` file is maintained in the repository showing required variable names without real values.

---

## 4. Input validation & data integrity

- All API input is validated at the boundary using **Pydantic** models (native to FastAPI), rejecting malformed or unexpected data before it reaches business logic.
- All database queries use the ORM (SQLAlchemy) or parameterized queries — raw string-concatenated SQL is prohibited, to prevent SQL injection.
- File uploads (PDF reports for AI analysis) are restricted by file type and a maximum size limit, and are scanned for type validity (not just extension) before processing.

---

## 5. Authorization

- Every data access is scoped to the authenticated user: a user can only read or modify portfolios, assets, lots, price levels, and analyses that belong to their own account.
- This scoping is enforced at the service/repository layer, not only in the UI, so that a direct API call cannot bypass it.

---

## 6. Transport & infrastructure

- All traffic is served over **HTTPS** in any deployed environment; local development may use HTTP.
- CORS is explicitly configured to only allow the known frontend origin(s), not wildcard (`*`), once a production frontend URL exists.
- Database connections use TLS when the database is hosted remotely (e.g. Azure Database for PostgreSQL).

---

## 7. Sensitive data handling

- Financial data (portfolio values, purchase prices, gains/losses) is treated as sensitive personal data: never logged in plaintext in application logs.
- OAuth tokens received from Google/Microsoft are never persisted beyond what is needed to maintain the session; raw third-party access tokens are not stored long-term unless required for a specific feature (and if so, encrypted at rest).

---

## 8. Dependency hygiene

- Dependencies are pinned (exact versions) in `requirements.txt` / `pyproject.toml` and `package.json`.
- A dependency vulnerability check (e.g. `pip-audit` for Python, `npm audit` for the frontend) is run as part of the development workflow before each release milestone.

---

## 9. Rationale

This spec intentionally favors well-established, low-dependency security mechanisms (Authlib, JWT, bcrypt, Pydantic validation) over external identity/security-as-a-service platforms, in line with the project's goal of remaining portable across hosting environments (Azure today, potentially local or another provider later) and free of recurring licensing costs.
