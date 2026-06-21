# Spec 00e — Prerequisites & Manual Setup

**Status:** Approved
**Type:** Cross-cutting engineering spec
**Applies to:** Initial project setup, before any code can run end-to-end
**References:** Spec 00b (Security Practices), Spec 00d (Containerization & Deployment), Spec D01 (Authentication & Identity)

---

## 1. Purpose

Document every manual, one-time setup step that must be completed outside the codebase before the system can run end-to-end. These steps are not code, so they cannot be captured by a domain or technical spec — but if any of them is missed, parts of the system will fail silently or with confusing errors. This spec is the canonical checklist.

This spec is **not** a "how to deploy" guide; it is a list of external dependencies (third-party app registrations, accounts, credentials) that must exist before the system is functional.

---

## 2. OAuth application registrations

The system requires registering one OAuth 2.0 application with each external identity provider it supports (per Spec D01).

### 2.1 Google OAuth

- **Where:** Google Cloud Console (`https://console.cloud.google.com`).
- **What:** create a new project (or reuse an existing one), then register an OAuth 2.0 Client ID under "APIs & Services → Credentials".
- **Application type:** Web application.
- **Required configuration:**
  - Authorized redirect URI(s): one per environment (local dev, production). Format: `<base-url>/auth/google/callback`.
  - Authorized JavaScript origins: the frontend base URL(s).
  - OAuth consent screen: minimum required fields (app name, support email, scopes: `openid`, `email`, `profile`).
- **Output (secrets):** Client ID and Client Secret. Store as environment variables (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`) per Spec 00b, Section 3.
- **Cost:** free, no usage charges relevant to this project's scale.

### 2.2 Microsoft OAuth (Azure Entra ID)

- **Where:** Azure Portal → Azure Entra ID → App registrations (`https://entra.microsoft.com` or `https://portal.azure.com`).
- **What:** register a new application.
- **Required configuration:**
  - Supported account types: choose "Accounts in any organizational directory and personal Microsoft accounts" (to allow both work and personal Microsoft accounts).
  - Redirect URI(s): one per environment, type "Web", format `<base-url>/auth/microsoft/callback`.
  - API permissions: `openid`, `email`, `profile`, `User.Read` (delegated).
  - Generate a client secret under "Certificates & secrets".
- **Output (secrets):** Application (client) ID and Client Secret. Store as environment variables (`MICROSOFT_OAUTH_CLIENT_ID`, `MICROSOFT_OAUTH_CLIENT_SECRET`) per Spec 00b, Section 3.
- **Cost:** free for this use case.

---

## 3. Market & FX data provider accounts

The system uses two distinct categories of external data, per Spec D09:

### 3.1 Market data provider (stock/ETF/crypto prices)

Two adapters are supported in v1: Twelve Data and Finnhub. The active provider is chosen via `market_data.provider` in `config.yaml` (Spec 00f §7.8). Each requires its own free-tier API key:

- **Twelve Data** (default): `MARKET_DATA_TWELVE_DATA_API_KEY` — obtained free from `https://twelvedata.com`. Free tier allows 800 calls/day.
- **Finnhub**: `MARKET_DATA_FINNHUB_API_KEY` — obtained free from `https://finnhub.io`. Free tier allows 60 calls/minute.

At minimum, the API key for the **currently active** provider must be set. The other may remain unset.

### 3.2 FX data provider (foreign exchange rates)

The FX provider in v1 is **Frankfurter** (`https://frankfurter.dev`), which sources its data from the European Central Bank. It requires no API key, no signup, and has no usage limits. No environment variable is required.

---

## 4. AI provider accounts (for PDF analysis)

The system uses one of three configurable LLM providers (Anthropic Claude, OpenAI, or Google Gemini) to analyze financial reports uploaded as PDFs, per Spec D07. The active provider is selected via `ai.provider` in `config.yaml` (Spec 00f §7.6). Each provider requires its own API key:

- **Anthropic:** `AI_ANTHROPIC_API_KEY` — obtained from `https://console.anthropic.com`.
- **OpenAI:** `AI_OPENAI_API_KEY` — obtained from `https://platform.openai.com`.
- **Google Gemini:** `AI_GEMINI_API_KEY` — obtained from `https://aistudio.google.com`.

At minimum, the API key for the **currently active provider** must be set. The keys for inactive providers may be unset; their absence does not block startup.

All three providers charge per-token usage. Pricing varies by provider and model and changes over time; consult the provider's current pricing page. The project owner is responsible for monitoring usage via each provider's dashboard.

---

## 5. Local development prerequisites

The following must be installed on any developer machine before running the project:

| Tool | Purpose | Notes |
|---|---|---|
| Docker Desktop | Run the containerized stack locally | Free per Spec 00d, Section 2 |
| Git | Version control | — |
| Code editor | Development | Visual Studio Code recommended (matches the master's program toolchain) |

No local installation of Python, Node.js, or PostgreSQL is required — all run inside containers.

---

## 6. Environment variables checklist

Before the system starts for the first time, a `.env` file (excluded from version control) must be created at the project root with at minimum the variables listed below. A `.env.example` file is maintained in the repository with the same variable names and placeholder values.

| Variable | Purpose | Source |
|---|---|---|
| `JWT_SIGNING_KEY` | Sign session tokens (Spec 00b §2) | Generate a random secure string locally |
| `DATABASE_URL` | PostgreSQL connection string | Matches Docker Compose service definition |
| `REDIS_URL` | Redis connection string (used by Celery for async PDF analysis, Spec D07 §2) | Matches Docker Compose service definition |
| `GOOGLE_OAUTH_CLIENT_ID` | Google login | Section 2.1 of this spec |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google login | Section 2.1 of this spec |
| `MICROSOFT_OAUTH_CLIENT_ID` | Microsoft login | Section 2.2 of this spec |
| `MICROSOFT_OAUTH_CLIENT_SECRET` | Microsoft login | Section 2.2 of this spec |
| `MARKET_DATA_TWELVE_DATA_API_KEY` | Twelve Data market data provider | Section 3.1 of this spec |
| `MARKET_DATA_FINNHUB_API_KEY` | Finnhub market data provider | Section 3.1 of this spec |
| `AI_ANTHROPIC_API_KEY` | Anthropic Claude provider | Section 4 of this spec |
| `AI_OPENAI_API_KEY` | OpenAI GPT provider | Section 4 of this spec |
| `AI_GEMINI_API_KEY` | Google Gemini provider | Section 4 of this spec |
| `FRONTEND_BASE_URL` | Used for OAuth redirects and CORS | e.g. `http://localhost:5173` in dev |
| `BACKEND_BASE_URL` | Used by the frontend to reach the API | e.g. `http://localhost:8000` in dev |

---

## 7. Rationale

Capturing these prerequisites explicitly in a spec — rather than implicitly in a README or in the implementer's head — is part of the Spec Driven Development discipline: anyone (a new developer, the master's program evaluator, an AI assistant generating code) should be able to read the specs and know not only *what to build* but *what must exist for the build to function*. Without this spec, a working codebase plus a missing OAuth registration would result in an authentication system that compiles, passes its tests, and still cannot log anyone in — a class of failure that is much cheaper to prevent than to debug.
