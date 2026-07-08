# Changeset C09 — Azure Deployment (Production Runbook)

**Status:** Implemented
**Type:** Cross-spec changeset / operational runbook
**Triggered by:** First production deployment of the system (realizes Spec 00d §5, "Deployment strategy (v1)").
**Affects implementations of:** Spec 00b (Security Practices — cookies, CSRF), Spec 00d (Containerization & Deployment), Changeset C01 (auth transport model).

---

## 0. How to read this document

This is **not** a new spec. It records what was actually done the first time the system was deployed to Azure (2026-07-07/08), including two real bugs found and fixed *in production* that the original design (Spec 00b, Changeset C01) did not anticipate. Spec 00d §5 said Azure deployment was "deferred until first deployed" — this changeset is that realization, kept as the reference for **future redeployments**, so the same debugging isn't repeated from scratch.

Read §4 (runbook) when you need to redeploy. Read §5 (gotchas) before you conclude a deploy command "worked" just because it printed `Succeeded`. Read §6 if you're touching CSRF/cookie code and need to know why it looks the way it does.

---

## 1. Architecture deployed

```
AZURE (northeurope) — account rcepeda@euralsoft.com, tenant euralsoft.com (Eural)
Subscription: "Azure subscription 1" (401af127-1a3c-4ea1-a029-270e154d6bb0)
Resource Group: VisualStudioOnline-D8AAAD9D5321436DBEA800C13A773885

Container Apps Environment: portfolio-ia-env
Domain: icysand-40c562ef.northeurope.azurecontainerapps.io

  portfolio-ia-backend   FastAPI + Uvicorn, port 8000, min=1 max=2, 0.5 CPU / 1GB RAM, ingress external
  portfolio-ia-worker    Celery worker, no ingress, min=1 max=1, 0.5 CPU / 1GB RAM
  portfolio-ia-frontend  Nginx + static assets, port 80, min=0 max=2, 0.25 CPU / 0.5GB RAM, ingress external

Azure Database for PostgreSQL Flexible Server: portfolio-ia-db
  PostgreSQL 16, Standard_B1ms, 32GB storage, database "bigschool"
  Firewall: AllowAzureServices + AllowMyIP

External:
  GitHub Container Registry — ghcr.io/romercepeda/tfm-bigschool/{backend,frontend}:latest (public images)
  Upstash Redis — outside Azure, free tier, 10k commands/day
```

**URLs:**

| Service | URL |
|---|---|
| Frontend | `https://portfolio-ia-frontend.icysand-40c562ef.northeurope.azurecontainerapps.io` |
| Backend | `https://portfolio-ia-backend.icysand-40c562ef.northeurope.azurecontainerapps.io` |
| Swagger UI | `https://portfolio-ia-backend.icysand-40c562ef.northeurope.azurecontainerapps.io/docs` |
| PostgreSQL | `portfolio-ia-db.postgres.database.azure.com:5432` |

**Cost estimate:** ~20-21 €/month (PostgreSQL B1ms ~12€, backend Container App ~4€, worker ~4€, frontend ~0-1€ since it scales to zero, Redis and GHCR free tier).

**Important — this is deployed under Eural's Azure account, not a personal one.** Confirmed 2026-07-08: `rcepeda@euralsoft.com`, tenant "EURAL SPAIN SOFT TECHNOLOGY S.L". Don't assume a fresh machine/session has this logged in.

---

## 2. Prerequisites for whoever redeploys

- **Azure CLI**: may be installed but not on `PATH`. On the machine this was first deployed from, the binary is at `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd`. Check `where az` first; if not found, check that path before reinstalling.
- **Login check**: run `az account show` before touching anything. It must resolve to tenant `euralsoft.com`, subscription `401af127-1a3c-4ea1-a029-270e154d6bb0`. If not logged in, `az login` (interactive/device-code — this account uses a normal user login, not a service principal).
- **Docker Desktop** running locally (for `docker build`/`docker push`).
- **GHCR push access**: images are pushed to `ghcr.io/romercepeda/tfm-bigschool/*` under the `romercepeda` GitHub account. The Container Apps already have the pull credential configured as a secret named `ghcrio-romercepeda` (registry `ghcr.io`, username `romercepeda`) — this doesn't need to be redone unless the token is rotated (see §8).

---

## 3. Environment variables (backend + worker Container Apps)

Set directly on `portfolio-ia-backend` and `portfolio-ia-worker` (not read from a `.env` file in production — Container Apps injects them):

```
DATABASE_URL = postgresql+asyncpg://portfolioadmin:<password>@portfolio-ia-db.postgres.database.azure.com/bigschool?ssl=require
REDIS_URL = rediss://default:<password>@<host>.upstash.io:6379   # rediss://, NOT redis:// — see §5.7
JWT_SIGNING_KEY = <random, generated with: python -c "import secrets; print(secrets.token_hex(32))">
FRONTEND_BASE_URL = https://portfolio-ia-frontend.icysand-40c562ef.northeurope.azurecontainerapps.io
BACKEND_BASE_URL = https://portfolio-ia-backend.icysand-40c562ef.northeurope.azurecontainerapps.io
GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET
MICROSOFT_OAUTH_CLIENT_ID / MICROSOFT_OAUTH_CLIENT_SECRET
MARKET_DATA_TWELVE_DATA_API_KEY / MARKET_DATA_FINNHUB_API_KEY / MARKET_DATA_EODHD_API_KEY
AI_ANTHROPIC_API_KEY / AI_OPENAI_API_KEY / AI_GEMINI_API_KEY
```

`BACKEND_BASE_URL` matters beyond OAuth callback construction: as of this changeset, the backend also reads it to decide the `Secure` flag on auth cookies (see §6.3) — it must start with `https://` in any real deployment, or cookies silently stop being marked `Secure`.

**`DATABASE_URL` and `REDIS_URL` must be set identically on both `portfolio-ia-backend` and `portfolio-ia-worker`** — they are two separate Container Apps with independently-set env vars, not a shared config. §5.7 and §5.8 are both instances of these silently drifting apart on the worker specifically (wrong Redis scheme, then a literal unreplaced password placeholder) without anyone noticing until a report upload actually exercised that path.

**Frontend** doesn't read environment variables at runtime (it's a static Nginx build) — it needs `VITE_BACKEND_BASE_URL` as a **Docker build-arg** at image build time (see §4.2). There is no frontend Container App env var to set.

**PowerShell note:** the DB password contains `!`. Pass it through an intermediate variable in PowerShell, not inline, to avoid escaping issues:
```powershell
$env:PGPASSWORD_TEMP = "<password>"
$connectionString = "postgresql://portfolioadmin:$env:PGPASSWORD_TEMP@portfolio-ia-db.postgres.database.azure.com/bigschool?sslmode=require"
```

---

## 4. Redeploy runbook

Run from the repo root (`D:\SourcesControl\RomerPersonal\TFM_BigSchool`). Use the **short git SHA of the commit being deployed** as the revision suffix (§5.1 explains why this is mandatory, not optional).

### 4.1 Backend + worker (same image)

```powershell
docker build `
  --tag ghcr.io/romercepeda/tfm-bigschool/backend:latest `
  --file ./backend/Dockerfile `
  ./backend

docker push ghcr.io/romercepeda/tfm-bigschool/backend:latest

$sha = git rev-parse --short HEAD
$azPath = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
$rg = "VisualStudioOnline-D8AAAD9D5321436DBEA800C13A773885"

& $azPath containerapp update `
  --name "portfolio-ia-backend" `
  --resource-group $rg `
  --image "ghcr.io/romercepeda/tfm-bigschool/backend:latest" `
  --revision-suffix "deploy-$sha"

& $azPath containerapp update `
  --name "portfolio-ia-worker" `
  --resource-group $rg `
  --image "ghcr.io/romercepeda/tfm-bigschool/backend:latest" `
  --revision-suffix "deploy-$sha"
```

### 4.2 Frontend

```powershell
docker build `
  --tag ghcr.io/romercepeda/tfm-bigschool/frontend:latest `
  --file ./frontend/Dockerfile `
  --build-arg VITE_BACKEND_BASE_URL=https://portfolio-ia-backend.icysand-40c562ef.northeurope.azurecontainerapps.io `
  ./frontend

docker push ghcr.io/romercepeda/tfm-bigschool/frontend:latest

& $azPath containerapp update `
  --name "portfolio-ia-frontend" `
  --resource-group $rg `
  --image "ghcr.io/romercepeda/tfm-bigschool/frontend:latest" `
  --revision-suffix "deploy-$sha"
```

### 4.3 Verify — don't trust the CLI's "Succeeded" alone (§5.1)

```powershell
& $azPath containerapp revision list --name "portfolio-ia-backend" --resource-group $rg --output table
& $azPath containerapp revision list --name "portfolio-ia-frontend" --resource-group $rg --output table
```

Confirm a **new** revision name (containing `deploy-$sha`) shows `HealthState: Healthy` and `TrafficWeight: 100`.

Then hit the real endpoint with `curl`, reproducing what a browser would send (see §7 for the full checklist) — the deploy is only actually verified once this passes, not when `az` exits 0.

### 4.4 Migrations (only if the schema changed)

```powershell
$env:PGPASSWORD_TEMP = "<password>"
$connectionString = "postgresql://portfolioadmin:$env:PGPASSWORD_TEMP@portfolio-ia-db.postgres.database.azure.com/bigschool?sslmode=require"

docker run --rm `
  -e DATABASE_URL=$connectionString `
  -w /app `
  ghcr.io/romercepeda/tfm-bigschool/backend:latest `
  python -m alembic upgrade head
```

### 4.5 Changing an env var without a new image

```powershell
& $azPath containerapp update --name "portfolio-ia-backend" --resource-group $rg --set-env-vars NOMBRE_VAR="valor_nuevo"
```

This *does* reliably create a new revision (the template actually changes), unlike the image-only case in §5.1.

---

## 5. Gotchas encountered — root-caused, not guessed

### 5.1 `az containerapp update --image ...:latest` does not force a redeploy

Both apps use the mutable `:latest` GHCR tag. `containerapp update` diffs the **container spec string**, not the registry digest. If the image reference string is byte-identical to the currently active revision (which it always is when you only bump `:latest`), Azure keeps serving the *old* revision — while still returning `provisioningState: Succeeded` on the update call. There is no error, no warning. The only way to notice is that the live behavior doesn't match the new code.

Confirmed 2026-07-08: pushed a new backend image with a bug fix, ran `containerapp update --image`, got `Succeeded`, but `curl` against the live endpoint showed the fix wasn't there — still running the previous day's revision.

**Fix, mandatory on every deploy:** always pass `--revision-suffix <unique-value>` (§4 commands already do this). Confirm with `revision list -o table` that a genuinely new revision name exists with `Healthy` / `TrafficWeight 100` (§4.3). Do not trust the `update` command's own JSON output.

### 5.2 Cross-host CSRF cookie: `document.cookie` cannot read a cookie set by a different hostname

**Symptom:** login worked once, then every subsequent `POST` returned 403 ("CSRF token missing or invalid"), including a later `POST /auth/guest` after a backend restart.

**Root cause:** the CSRF double-submit cookie (`pi_csrf`, Changeset C01 §1) was set by the backend with no explicit `Domain=` attribute, making it a **host-only cookie** scoped to `portfolio-ia-backend...`. The frontend (`api/client.ts`) read it via `document.cookie` to echo it in the `X-CSRF-Token` header — but `document.cookie`, executed in a page loaded from `portfolio-ia-frontend...`, can only see cookies belonging to *that exact host*. Frontend and backend are different hostnames in this Azure deployment (they only share `localhost` in local dev, where cookies aren't port-scoped, which is why this never surfaced locally).

The browser *does* still send the cookie to the backend automatically (cookie attachment is based on the request's target host, not the page's origin) — so the backend's middleware sees `cookie_value is not None` and demands the header, while the frontend's JS can never produce that header. Every state-changing request after the first login was doomed.

**Fix:** the login response body now also carries the CSRF token (`LoginSessionOut.csrf_token`, `backend/app/auth/schemas.py` + `backend/app/api/auth.py`). The frontend keeps it in memory (`frontend/src/state/auth-state.ts`) instead of reading `document.cookie` (`frontend/src/api/client.ts`, and a duplicate copy of the same broken logic in `frontend/src/api/analyses.ts` for PDF uploads). The `pi_csrf` cookie itself is unchanged and still travels to the backend for the double-submit comparison — only *how the frontend learns the value* changed.

### 5.3 Corollary of 5.2: login itself can get locked out by a leftover cookie

**Symptom:** after deploying the 5.2 fix, login itself started failing with 403 for a browser that had already been used to test the broken version.

**Root cause:** the CSRF middleware only skips validation when the `pi_csrf` cookie is **absent**. A browser that already holds *any* `pi_csrf` cookie from a prior session (even one where 5.2 was still broken and login never truly "completed" in the frontend's eyes) will have that cookie sent automatically on the next login attempt. The frontend, on a fresh page load, has no CSRF value in memory yet (it only learns it *from* a successful login response) — chicken-and-egg. The very first `POST /auth/guest` was rejected before it could ever return a fresh token.

**Fix:** `backend/app/auth/csrf.py` now exempts the session-issuing endpoints (`/auth/register`, `/auth/login`, `/auth/guest`) from CSRF validation entirely, regardless of any existing cookie. These endpoints don't act on an existing session — there is no ambient authority for CSRF to protect there, and gating them creates exactly this lockout. `/auth/logout`, `/auth/change-password`, and everything else that requires an existing `pi_session` remain fully protected.

**Operational takeaway:** if login ever breaks again for one browser but `curl` from a clean cookie jar works fine, suspect a leftover cookie before suspecting the deployment — clearing cookies for the backend's domain in DevTools is the fastest unblock while investigating.

### 5.4 `Secure` cookie flag was hardcoded `False`

`_set_session_cookies` (`backend/app/api/auth.py`) had `secure=False` hardcoded with a `# set True when serving over HTTPS` comment that was never acted on — a real deviation from Spec 00b §6. Not the cause of the 403s above, but fixed alongside: `secure` is now derived from whether `BACKEND_BASE_URL` starts with `https://` (true in Azure, false in local dev where it's `http://localhost:8000` and a `Secure` cookie would simply be dropped by the browser).

### 5.5 Celery worker needs its own launch script baked into the image

Docker Compose's model — one image, different `command:` per service — has no equivalent in Azure Container Apps in the way this project used it. `portfolio-ia-worker` needs a dedicated entry point. Fix: `backend/start-worker.sh` (`exec celery -A app.worker:celery_app worker --loglevel=info`) is now `COPY`'d into the image and `chmod +x`'d in `backend/Dockerfile`. The worker Container App's command is configured separately to invoke it (already set on the existing `portfolio-ia-worker` app — not something `containerapp update --image` touches, so it doesn't need to be repeated on every redeploy, only if the worker's command itself changes).

### 5.6 The Celery Redis result backend crashes uploads against Upstash (and nothing reads it anyway)

**Symptom (found 2026-07-08, a day after the initial deployment):** `POST /portfolios/{id}/holdings/{id}/ai-reports` (PDF report upload) returned 500. Backend logs showed `redis.exceptions.ConnectionError: Connection closed by server` raised from inside `send_task` → `on_task_call`, after ~20 retries of `celery.backends.redis: Connection to Redis lost`.

**Root cause:** `backend/app/worker/__init__.py` configured Redis as **both** the Celery broker and the **result backend**. The result backend opens a persistent pubsub subscription per task on `send_task()` so a later `AsyncResult.get()` can consume the result efficiently — but nothing in this codebase ever calls `AsyncResult` or `.get()`; job status is tracked entirely via the `AnalysisJob` DB row, polled through `GET /ai-reports/jobs`. That pubsub connection was pure unread overhead, and Upstash killed it, which Celery's retry logic exhausted and then raised instead of enqueueing.

**Fix:** removed `backend=` from the `Celery(...)` constructor and added `task_ignore_result=True`. Verified locally that `send_task` now goes through `celery.backends.base.DisabledBackend` — no Redis round-trip for results at all.

### 5.7 `REDIS_URL` was using the plain (non-TLS) `redis://` scheme

**Symptom:** even after fixing 5.6, the worker container couldn't connect to Redis *at all* on startup: `consumer: Cannot connect to redis://...upstash.io:6379//: Connection closed by server`, retried up to 100 times.

**Root cause:** the `REDIS_URL` configured on both `portfolio-ia-backend` and `portfolio-ia-worker` used the `redis://` (plain TCP) scheme. Upstash Redis only accepts TLS connections on its endpoint — a plain-TCP Redis handshake gets its connection closed immediately by the server. This affected the broker connection too (not just the result-backend pubsub from 5.6), and is likely part of why the original `on_task_call` pubsub subscribe in 5.6 kept failing so aggressively.

**Fix:** changed the scheme to `rediss://` (same host/port) on both container apps:
```powershell
& $azPath containerapp update --name "portfolio-ia-backend" --resource-group $rg --set-env-vars "REDIS_URL=rediss://default:<password>@<host>.upstash.io:6379"
& $azPath containerapp update --name "portfolio-ia-worker" --resource-group $rg --set-env-vars "REDIS_URL=rediss://default:<password>@<host>.upstash.io:6379"
```
Worker logs confirmed `Connected to rediss://...` and `celery@... ready.` immediately after. Note: Celery logs a `Secure redis scheme specified (rediss) with no ssl options, defaulting to insecure SSL behaviour` warning — harmless here (still TLS-encrypted, just without custom cert verification options), not investigated further since it isn't blocking.

**When copying `REDIS_URL` from the Upstash console, always use the `rediss://` connection string, not `redis://`**, even though Upstash's dashboard sometimes shows both.

### 5.8 The worker's `DATABASE_URL` had a literal, never-replaced placeholder password

**Symptom:** after fixing 5.6 and 5.7, the worker received and ran the task, but it failed with `InvalidPasswordError: password authentication failed for user "portfolioadmin"`.

**Root cause:** `portfolio-ia-worker`'s `DATABASE_URL` env var was `postgresql+asyncpg://portfolioadmin:TU_PASSWORD_DB@...` — the `TU_PASSWORD_DB` placeholder was never swapped for the real password when the worker container app was created, even though `portfolio-ia-backend`'s `DATABASE_URL` had the correct password all along. Since the worker never has ingress/logs anyone actively watches, this went unnoticed until a report upload actually reached the point of writing to the DB.

**Fix:** copied the real password from the backend's `DATABASE_URL` into the worker's.

**Operational takeaway:** whenever `portfolio-ia-backend` and `portfolio-ia-worker` are meant to share a config value (`DATABASE_URL`, `REDIS_URL`), **diff them explicitly** after any setup or redeploy —
```powershell
& $azPath containerapp show --name "portfolio-ia-backend" --resource-group $rg --query "properties.template.containers[0].env" -o json
& $azPath containerapp show --name "portfolio-ia-worker" --resource-group $rg --query "properties.template.containers[0].env" -o json
```
— don't assume they were set identically just because they were set at the same time.

### 5.9 Verifying with PowerShell's `Invoke-WebRequest` can give false negatives

During verification, `Invoke-WebRequest -WebSession` intermittently failed to carry a cookie across two calls in the same script in a way that looked like a real CSRF failure but wasn't reproducible with `curl`. **Prefer `curl` (available in Git Bash / `PowerShell` via the bundled `curl.exe`) for any CSRF/cookie verification** — it's the ground truth used throughout this changeset. If `Invoke-WebRequest` disagrees with `curl`, trust `curl`.

### 5.10 A failed `.delay()` call leaves the AnalysisJob row orphaned in "queued" forever

**Symptom (found 2026-07-08, after fixing 5.6-5.8):** the header-bar's pending-jobs badge stayed stuck on a count (4 in the observed case) that never went down, even though no upload was actually in flight.

**Root cause:** `create_upload_and_job` (`backend/app/services/ai_report_service.py`) commits the `AnalysisJob` row as `status="queued"` **before** calling `analyze_report_task.delay(job.id)` — deliberately, so the worker is guaranteed to find the row once it picks up the task (see the code comment there). But during the 5.6-5.8 outage, `.delay()` itself was throwing (broker unreachable), which raised a 500 back to the client — while the `"queued"` row had *already been committed*. Nothing was ever going to transition that row out of `"queued"`: no worker ever received the task, and there was no other code path watching for "enqueue never actually happened." `GET /ai-reports/jobs?status_filter=queued,running` (the badge's data source) counted these forever.

Four such rows accumulated in production during the 5.6-5.8 outage window and had to be cleaned up manually:
```sql
UPDATE analysis_jobs SET status='failed', last_error='...', completed_at=now()
WHERE status IN ('queued','running') AND attempt_count=0 AND started_at IS NULL;
```
(`attempt_count=0 AND started_at IS NULL` scopes this to rows a worker never touched at all — never match a job that's legitimately mid-retry.)

**Fix:** `create_upload_and_job` now wraps `.delay()` in try/except; on failure it marks the job `"failed"` with an explanatory `last_error` before re-raising, so a broker outage now produces a clean failed job instead of a silent leak. This is defense-in-depth on top of 5.6-5.8 actually being fixed — it stops this *specific* failure mode from recurring for any *future* broker hiccup, whatever the cause.

**Operational takeaway:** if the pending-jobs badge is ever stuck again, check for `AnalysisJob` rows with `status IN ('queued','running') AND started_at IS NULL` — that combination means the row was never picked up by any worker at all, which after this fix should no longer be reachable via the upload endpoint, but could still happen if something enqueues jobs outside of `create_upload_and_job`.

---

## 6. Summary of code changes introduced by this changeset

| File | Change |
|---|---|
| `backend/app/auth/csrf.py` | Exempt `/auth/register`, `/auth/login`, `/auth/guest` from CSRF validation (§5.3). |
| `backend/app/auth/schemas.py` | `LoginSessionOut` gains `csrf_token: str`. |
| `backend/app/api/auth.py` | `_build_login_response` includes `csrf_token`; `_set_session_cookies` derives `secure` from `BACKEND_BASE_URL` (§5.4). |
| `frontend/src/api/types.ts` | `LoginSessionOut` gains `csrf_token: string`. |
| `frontend/src/state/auth-state.ts` | Holds the CSRF token in memory (`getCsrfToken`/`setAuthState`), set at login, cleared at logout. |
| `frontend/src/screens/login-screen.ts` | Passes `res.session.csrf_token` into `setAuthState`. |
| `frontend/src/api/client.ts` | Reads the CSRF token from `auth-state.ts` instead of `document.cookie`. |
| `frontend/src/api/analyses.ts` | Same fix applied to the PDF-upload fetch wrapper, which had its own duplicate (and equally broken) `document.cookie` reader. |
| `backend/Dockerfile`, `backend/start-worker.sh` | Worker launch script baked into the image (§5.5) — must have LF line endings, not CRLF (a Windows editor/tool reintroducing CRLF in the working tree, even with `.gitattributes eol=lf`, silently breaks the baked-in script; `git diff` shows nothing because the *committed blob* is already normalized — only the on-disk file was wrong. Verify with `docker run --rm <image> sh -c "cat -A /start-worker.sh"` and confirm no `^M`/`$` mix before trusting a build). |
| `backend/app/worker/__init__.py` | Removed the Redis result backend, `task_ignore_result=True` (§5.6). |
| `frontend/src/screens/login-screen.ts` | Removed the hardcoded default email value on the login form. |
| `backend/app/services/ai_report_service.py` | `create_upload_and_job` marks the job `"failed"` if `.delay()` raises, instead of leaving it orphaned in `"queued"` (§5.10). |

This does **not** change Changeset C01's acceptance criteria — a `POST` without a valid `X-CSRF-Token` still returns 403 for every endpoint that requires an existing session. It narrows *which* endpoints require the header (session-issuing ones no longer do) and changes *how* the frontend obtains the value (body instead of cross-host cookie read).

---

## 7. Post-deploy verification checklist

Run this after every backend redeploy, from a shell with `curl`:

```bash
BACKEND="https://portfolio-ia-backend.icysand-40c562ef.northeurope.azurecontainerapps.io"
FRONTEND_ORIGIN="https://portfolio-ia-frontend.icysand-40c562ef.northeurope.azurecontainerapps.io"

# 1. Login returns csrf_token in the body
curl -s -c cookies.txt -X POST "$BACKEND/auth/guest" -H "Content-Type: application/json" \
  -H "Origin: $FRONTEND_ORIGIN" -d '{"email":"verify@test.com"}' | grep -o '"csrf_token":"[^"]*"'

# 2. A state-changing request WITH the correct header succeeds (use the token from step 1)
curl -s -b cookies.txt -X POST "$BACKEND/portfolios" -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" -H "Origin: $FRONTEND_ORIGIN" \
  -d '{"name":"verify","base_currency":"EUR"}' -w "\n%{http_code}\n"   # expect 201

# 3. The same request WITHOUT the header is rejected
curl -s -b cookies.txt -X POST "$BACKEND/portfolios" -H "Content-Type: application/json" \
  -H "Origin: $FRONTEND_ORIGIN" -d '{"name":"verify","base_currency":"EUR"}' -w "\n%{http_code}\n"  # expect 403

# 4. Login works even with a stale pi_csrf cookie already in the jar (§5.3 regression guard)
curl -s -b cookies.txt -X POST "$BACKEND/auth/guest" -H "Content-Type: application/json" \
  -H "Origin: $FRONTEND_ORIGIN" -d '{"email":"verify2@test.com"}' -w "\n%{http_code}\n"  # expect 200
```

If the worker image changed, also confirm a report upload actually completes end to end (catches §5.6-§5.8 class of bugs, which a plain `curl` health check on the backend alone won't surface — those only show up once a task actually reaches the worker):

```bash
# after uploading a PDF via POST .../ai-reports (expect 202, with a job_id)
curl -s -b cookies.txt "$BACKEND/ai-reports/jobs" -H "Origin: $FRONTEND_ORIGIN"
# poll until status is "completed" or "failed" (not stuck on "queued")
# a "failed" status with a last_error about the PDF/AI provider is fine (bad test file);
# a "failed"/stuck-"queued" status with no last_error, or a 500 on the POST itself, is not.
```

Also confirm the frontend is actually serving the new build, not a cached one:

```bash
curl -s "$FRONTEND_ORIGIN/" | grep -o '/assets/index-[A-Za-z0-9]*\.js'
# fetch that JS file and grep for a string only present in the new code, e.g.:
curl -s "$FRONTEND_ORIGIN/assets/index-XXXX.js" | grep -c "csrf_token"
```

---

## 8. Known pending items (out of scope of this changeset)

Carried over from the original deployment notes, still open:

- **GitHub token rotation**: a token was inadvertently exposed in logs during this deployment's debugging and was rotated. No further action needed, noted for awareness.
- **Zero Trust Access** (Cloudflare) as an extra auth layer in front of the backend — not implemented, purely a future option.
- **Automated PostgreSQL backups**: not yet verified as active on the Burstable tier. Needs checking before this is treated as durable storage.
- **Custom domain**: still on the default `*.azurecontainerapps.io` subdomains. If a custom domain is added later (e.g. `app.example.com` + `api.example.com` on the same registrable domain), the CSRF cookie could go back to being read via `document.cookie` with an explicit `Domain=` attribute shared across both — but the body-token approach from §5.2 works regardless and there's no need to revert it.
- **CI/CD**: still fully manual per Spec 00d §5, by explicit decision. This changeset's runbook (§4) is the manual process until that changes.
