# Spec 00f — Global Application Configuration

**Status:** Approved
**Type:** Cross-cutting engineering spec
**Applies to:** All backend components that consume tunable application-wide values
**References:** Spec D01 (Authentication & Identity), Spec D02 (Portfolio Management), Spec 00b (Security Practices)

---

## 1. Purpose

Centralize all tunable application-wide values (limits, toggles, defaults) in a single, version-controlled file, so that changes to behavior do not require code changes and the system has one canonical source of truth for "how the app is configured to behave today."

This spec defines **the configuration mechanism itself** — where the file lives, how it is read, how it is validated, and how individual values are referenced from other specs. It does **not** define every possible configuration value the system will ever have; new values will be added incrementally as new specs introduce them, always pointing back to this mechanism.

---

## 2. Scope: configuration vs secrets

This spec covers **behavioral configuration**: limits, feature toggles, default values, operational thresholds. These are non-sensitive values that describe how the application behaves.

This spec does **not** cover **secrets** (API keys, OAuth client secrets, JWT signing keys, database credentials). Secrets are managed via environment variables per Spec 00b, Section 3, and Spec 00e, Section 6. The two mechanisms coexist deliberately: secrets must never appear in a version-controlled file, while behavioral configuration benefits from being version-controlled so changes are visible in code review and can be rolled back.

---

## 3. Storage and format

- **File:** a single YAML file named `config.yaml`, located at the backend project root.
- **Version control:** committed to the repository. Any change to application behavior is therefore traceable through git history.
- **Format:** YAML, chosen for readability and native support for nested structures and comments.
- **Loaded:** once at application startup. The values are read into a strongly-typed configuration object (validated via Pydantic in the FastAPI backend, per Spec 00b, Section 4) and made available to the rest of the application as a single dependency.
- **Hot reload:** not supported in v1. Any change to `config.yaml` requires restarting the backend service to take effect.

---

## 4. Validation and startup behavior

- On startup, the backend **validates** the loaded configuration against its expected schema (types, allowed values, required fields).
- If the file is missing, unreadable, malformed (invalid YAML), or fails schema validation (missing required field, wrong type, value out of allowed range), **the application must not start**. The error is logged with a clear message identifying the offending field or the parse error.
- This is a deliberate **fail-fast** choice: silently falling back to defaults could mask configuration mistakes that lead to unexpected behavior in production (e.g. a typo that disables all login methods).
- Default values for individual fields are still defined in the schema, but they only apply to optional fields. Fields explicitly marked as required have no default and must be present in the file.

---

## 5. Administration

- In v1, the configuration file is edited **only by the project administrator** (the developer) directly in the repository, followed by a redeploy/restart.
- There is **no admin UI** in v1 to edit configuration values through the web application. This is out of scope per Section 9.
- This implies an operational consequence: any configuration change has the same friction as a code change (commit + deploy). This is acceptable in v1 and helps reinforce that configuration changes are deliberate, reviewed acts.

---

## 6. Naming and reference convention

- Configuration values are grouped under top-level sections (e.g. `portfolios:`, `authentication:`, `uploads:`).
- Throughout the rest of the specs, configuration values are referenced using **dot notation**: `portfolios.max_active_per_user`, `authentication.methods.google.enabled`, etc.
- Each domain spec that depends on a configurable value must reference it by name in the form `{section}.{key}` and **not** restate the default value as if it were fixed — the value of record is whatever the running configuration says.

---

## 7. Initial v1 configuration values

The following values are defined in v1. The list will grow as additional specs are written; each addition is recorded in the relevant spec and reflected here as part of the same change.

### 7.1 Portfolios (`portfolios`)

| Key | Type | Default | Description |
|---|---|---|---|
| `max_active_per_user` | integer ≥ 1 | `10` | Maximum number of active portfolios per user. See Spec D02, Section 9. |
| `name_max_length` | integer ≥ 1 | `60` | Maximum allowed length of a portfolio name. See Spec D02, Section 4. |

### 7.2 Uploads (`uploads`)

| Key | Type | Default | Description |
|---|---|---|---|
| `max_file_size_mb` | integer ≥ 1 | `20` | Maximum size (in megabytes) of any file uploaded to the system, including PDF financial reports for AI analysis. Applies to all upload endpoints. |

### 7.3 Authentication methods (`authentication.methods`)

Each authentication method defined in Spec D01 has its own `enabled` flag. All four are **enabled by default** in v1.

| Key | Type | Default | Description |
|---|---|---|---|
| `authentication.methods.google.enabled` | boolean | `true` | If `false`, the "Continue with Google" button is hidden from the login screen and the corresponding API endpoint rejects requests. |
| `authentication.methods.microsoft.enabled` | boolean | `true` | Same behavior, for Microsoft. |
| `authentication.methods.password.enabled` | boolean | `true` | Same behavior, for email + password. New password registrations are also rejected when disabled. |
| `authentication.methods.guest.enabled` | boolean | `true` | Same behavior, for guest accounts. New guest creation and guest re-entry are both rejected when disabled. |

**Behavior when a method is disabled:**

- The corresponding login option is **hidden** from the login screen UI.
- The corresponding backend endpoint **rejects requests** with a clear error indicating that the method is currently disabled. Defense-in-depth: the UI hiding the button is not the security boundary; the backend endpoint is.
- **Existing users** with `auth_provider` equal to the disabled method are **temporarily blocked** from logging in until the method is re-enabled. Their accounts and data are not deleted, modified, or migrated in any way — they are simply inaccessible while the method is off. Reactivating the method restores their ability to log in immediately.

**Accepted risk — administrator lockout:** the configuration mechanism does not prevent the administrator from disabling **all** authentication methods simultaneously, which would lock every user (including the administrator) out of the system. No cross-validation is performed in v1. The administrator is responsible for ensuring at least one method remains enabled. Recovery from a full lockout requires editing `config.yaml` directly in the repository or filesystem and restarting the application. This risk is documented here intentionally so it is not mistaken for an implementation gap.

### 7.4 Indicators (`indicators`)

Operational configuration for the indicator catalog and the scheduled job that updates technical indicators. See Spec D05 for full context.

| Key | Type | Default | Description |
|---|---|---|---|
| `indicators.scheduled_job.daily_run_hour_utc` | integer 0–23 | `2` | Hour of day (UTC) at which the daily indicator update job runs. Default is 02:00 UTC, after major American equity markets close. |

### 7.5 Alerts (`alerts`)

Configuration for the price-level alert engine. See Spec D06 for full context.

| Key | Type | Default | Description |
|---|---|---|---|
| `alerts.near_crossing_pct` | NUMERIC (between 0 and 1, exclusive) | `0.03` | A price level is considered "close to crossing" — and therefore surfaced in the Alerts Panel as a pre-alert — when the gap between the current price and the target is within this fraction of the current price. Default 3%. |

### 7.6 AI analysis (`ai`)

Configuration for the AI-powered PDF analysis pipeline. See Spec D07 for full context.

| Key | Type | Default | Description |
|---|---|---|---|
| `ai.provider` | enum (`anthropic` \| `openai` \| `gemini`) | `anthropic` | The active LLM provider used for PDF analyses. |
| `ai.anthropic.model` | string | `claude-opus-4-7` | Model identifier for the Anthropic adapter. |
| `ai.openai.model` | string | `gpt-4o` | Model identifier for the OpenAI adapter. |
| `ai.gemini.model` | string | `gemini-2.5-pro` | Model identifier for the Gemini adapter. |
| `ai.per_call_timeout_seconds` | integer ≥ 1 | `120` | Per-attempt LLM call timeout. |
| `ai.notifications.poll_interval_seconds` | integer ≥ 5 | `30` | Frontend polling interval for completed-job notifications. |

The retry policy itself (3 attempts, 1m/5m/15m backoff) is not configuration — it is part of the engineering contract per Spec D07 §7.

### 7.7 Internationalization (`i18n`)

Configuration for the user-facing language layer. See Spec D08 for full context.

| Key | Type | Default | Description |
|---|---|---|---|
| `i18n.default_language` | string (ISO 639-1 language code) | `es` | The language used for new accounts, unauthenticated screens, and as the last-resort fallback when a translation is missing. |
| `i18n.supported_languages` | list of language codes | `["es", "en"]` | The list of languages actively offered to users in the Configuration screen's language selector. Languages outside this list are not selectable, even if a `<locale>.json` file exists. |

### 7.8 Market data (`market_data`)

Configuration for the external market data integration. See Spec D09 for full context.

| Key | Type | Default | Description |
|---|---|---|---|
| `market_data.provider` | enum (`twelve_data` \| `finnhub`) | `twelve_data` | The active market data provider. |
| `market_data.twelve_data.base_url` | string | `https://api.twelvedata.com` | Base URL for the Twelve Data API. Configurable for testing/mocking. |
| `market_data.twelve_data.daily_call_budget` | integer | `800` | The known daily rate-limit ceiling on Twelve Data's free tier. Used by the prioritization logic to know when to stop gracefully. |
| `market_data.finnhub.base_url` | string | `https://finnhub.io/api/v1` | Base URL for the Finnhub API. |
| `market_data.finnhub.per_minute_call_budget` | integer | `60` | The known per-minute rate-limit ceiling for Finnhub's free tier. |

### 7.9 FX data (`fx_data`)

Configuration for the external foreign exchange data integration. See Spec D09 for full context.

| Key | Type | Default | Description |
|---|---|---|---|
| `fx_data.provider` | enum (`frankfurter`) | `frankfurter` | The active FX provider. Only `frankfurter` is supported in v1; the key exists for forward compatibility. |
| `fx_data.frankfurter.base_url` | string | `https://api.frankfurter.dev/v2` | Base URL for Frankfurter. |

---

## 8. Example `config.yaml`

```yaml
portfolios:
  max_active_per_user: 10
  name_max_length: 60

uploads:
  max_file_size_mb: 20

authentication:
  methods:
    google:
      enabled: true
    microsoft:
      enabled: true
    password:
      enabled: true
    guest:
      enabled: true

indicators:
  scheduled_job:
    daily_run_hour_utc: 2

alerts:
  near_crossing_pct: 0.03

ai:
  provider: anthropic
  anthropic:
    model: claude-opus-4-7
  openai:
    model: gpt-4o
  gemini:
    model: gemini-2.5-pro
  per_call_timeout_seconds: 120
  notifications:
    poll_interval_seconds: 30

i18n:
  default_language: es
  supported_languages:
    - es
    - en

market_data:
  provider: twelve_data
  twelve_data:
    base_url: https://api.twelvedata.com
    daily_call_budget: 800
  finnhub:
    base_url: https://finnhub.io/api/v1
    per_minute_call_budget: 60

fx_data:
  provider: frankfurter
  frankfurter:
    base_url: https://api.frankfurter.dev/v2
```

---

## 9. Out of scope for v1

- Admin UI to edit configuration values from within the web application.
- Hot reload of configuration without restarting the backend.
- Per-environment configuration overlays (e.g. `config.dev.yaml`, `config.prod.yaml`). For v1, environment-specific differences are handled via environment variables (for secrets) and via a single `config.yaml` per deployment.
- Per-user or per-portfolio overrides of global values.
- Audit log of configuration changes (git history serves this purpose informally in v1).
- Cross-validation rules (e.g. "at least one auth method must be enabled" — see Section 7.3 accepted risk).

---

## 10. Rationale

A YAML file in the repository is the simplest mechanism that satisfies the requirements: it is version-controlled, human-readable, supports nested structure, supports comments, and integrates trivially with Pydantic for typed validation. Choosing a database-backed configuration would have added complexity (migrations, an admin UI, hot-reload mechanics) that is disproportionate to v1 needs and would have made the configuration changes invisible to git history. The fail-fast validation policy aligns with the broader project principle of avoiding silent fallbacks for anything that affects user-facing behavior.

The decision to keep the four authentication method toggles as a first-class configuration concept — rather than hard-coded — reflects an anticipated operational reality: third-party identity providers (Google, Microsoft) occasionally have outages, app registrations expire, and the project owner may want to selectively turn methods off without a code change. This is the kind of operational flexibility that configuration is meant to provide.
