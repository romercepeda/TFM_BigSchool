---
name: verify-playwright
description: Launch and drive Portfolio IA (this app, a native-web-components SPA) with Playwright to visually verify a changeset/spec before calling it done. Use for every non-trivial change — backend-only changes that surface in the UI included, since the point is confirming the change actually renders/behaves as intended, not just that types/tests pass.
---

# Verifying Portfolio IA changes with Playwright

This project has standardized on Playwright, driven directly from Node.js
(no `chromium-cli`, which isn't installed in this Windows/Git-Bash
environment) for manual, AI-driven verification of every changeset before
it's committed. This skill exists so a session doesn't have to rediscover
the login flow, the route shapes, or the Windows path gotchas from scratch
— all of that cost real time the first time (Changeset C18) and is fully
solved below.

Reference: [spec-00c-testing-strategy.md](../../../specs/00-engineering/spec-00c-testing-strategy.md)
§7 documents this as project policy, not just a one-off.

## 1. Start the services

```bash
# Backend + DB + Redis + Celery worker (needed even for non-AI changes —
# cheap to leave running)
cd /d/SourcesControl/RomerPersonal/TFM_BigSchool
docker compose up -d backend db redis worker
curl -s http://localhost:8000/health   # wait for {"status":"ok",...}

# Frontend — Vite dev server, NOT the docker "frontend" container (both
# bind :5173; if the docker one is up, npm run dev silently falls back to
# :5174 and the backend's CORS then rejects it). Stop the docker one first
# if `docker compose ps frontend` shows it running.
docker compose stop frontend 2>/dev/null
cd frontend && npm run dev &          # serves http://localhost:5173
```

If Docker Desktop itself isn't running, start it and poll `docker info`
before `docker compose up` — don't just `sleep` a fixed guess, it can take
anywhere from a few seconds to ~60s cold.

## 2. The driver — plain Node.js + the `playwright` package

`playwright` is a devDependency of `frontend/package.json` (added in
Changeset C18 specifically so this doesn't require hunting for a stray
global/temp install again). Chromium's binary is cached machine-wide under
`%USERPROFILE%\AppData\Local\ms-playwright` — `npx playwright install
chromium` is a no-op if it's already there.

Write a throwaway script and run it with plain `node` from `frontend/`
(so `require('playwright')` resolves). **Use a `.cjs` extension, not
`.js`** — `frontend/package.json` has `"type": "module"`, so a plain `.js`
file is loaded as ESM and `require` throws `ReferenceError: require is not
defined`.

```js
// frontend/.playwright-scratch.cjs  (gitignored, see §5)
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('pageerror', err => console.log('[pageerror]', String(err)));

  // ... see §3 for the login + navigation recipe ...

  await browser.close();
})();
```

```bash
cd frontend && node .playwright-scratch.cjs
```

**Windows path gotcha:** Node on Windows does NOT do MSYS/Git-Bash path
translation. A screenshot path like `/tmp/foo.png` written from a Node
script does **not** land in Git-Bash's `/tmp` (which maps to
`C:\Users\<you>\AppData\Local\Temp`) — Node resolves it relative to the
current drive root instead (`D:\tmp\foo.png` or similar, often failing
outright). Always use an explicit Windows-style path with forward slashes
in the Node script — and get the **drive letter right**: this repo lives on
`D:`, so screenshot paths must start `D:/SourcesControl/...`, not `C:/...`
(easy to typo out of habit since scratch/temp files elsewhere in this
environment do live on `C:`). That same `D:/...` path is directly readable
afterwards via the `Read` tool.

## 3. Logging in

**Registration and guest login are both disabled** in `backend/config.yaml`
(`authentication.allow_registration: false`,
`authentication.methods.guest.enabled: false` — "temporarily disabled
2026-07-09, existing accounts only"). Do not waste time on
`/auth/register` or `/auth/guest`; both 403.

### The standing verification account

Use **`playwright@verify.com`**, password **`TestPass123!`**. This account
already existed in the local dev DB before Changeset C18 (a prior session's
convention); this changeset made its password known and reliable so future
sessions don't have to guess or re-derive it. It holds one asset (INTC) in
a portfolio called "TestPort" — a convenient, always-there fixture for
asset-detail / analysis-screen checks that doesn't touch Romer's real data.

**If a fresh/reset local DB doesn't have it yet** (or its password is
unknown — e.g. after `scripts/db.ps1 reset`), (re)provision it directly,
since `/auth/register` is disabled:

```bash
# 1. Hash the password the same way the app does:
docker compose exec -T backend python -c "
from app.auth.password import hash_password
print(hash_password('TestPass123!'))
"
# 2. Upsert the user with that hash (adjust email/hash as needed):
docker compose exec -T db psql -U postgres -d bigschool -c "
update users set password_hash='<hash from step 1>', auth_provider='password'
where email='playwright@verify.com';
"
# If the row doesn't exist at all, INSERT one instead (see any User model
# for required columns), or log in as any other existing password-auth
# account found via:
docker compose exec -T db psql -U postgres -d bigschool -c \
  "select email, auth_provider from users where auth_provider='password';"
```

Never do this against a non-local database. This is a local-dev-only
convenience for an account that owns no real financial data.

### Login script (do not `page.goto` a second time — see the gotcha below)

```js
await page.goto('http://localhost:5173/login');
await page.waitForSelector('input[type="email"]', { timeout: 15000 });
await page.fill('input[type="email"]', 'playwright@verify.com');
await page.fill('input[type="password"]', 'TestPass123!');
await page.click('#submit-btn');   // NOT button[type="submit"] — the button
                                    // has no type attribute, just id="submit-btn"
await page.waitForTimeout(1500);
```

**Critical gotcha — auth state is in-memory only, not a client-readable
cookie.** `frontend/src/state/auth-state.ts` keeps `currentUser` and the
CSRF token in a JS module variable, deliberately not in `document.cookie`
(frontend/backend live on different hosts in prod). There is also no
boot-time "restore session from refresh cookie" call in `main.ts`. **Any
`page.goto()` after login is a hard reload that wipes this state and bounces
you to `/login`**, even though the httpOnly refresh cookie is technically
still valid server-side. Consequence: **navigate exclusively via UI clicks
after logging in** (client-side SPA routing), never via a second
`page.goto`. Standard flow:

```js
await page.click('text=TestPort');                    // portfolio card
await page.waitForTimeout(1200);
await page.click('text=INTC');                         // holding row
await page.waitForTimeout(1200);
await page.click('button:has-text("Analysis")');       // or "Análisis" in ES
await page.waitForTimeout(1500);
```

Route shapes worth knowing (`frontend/src/router/routes.ts`) so you don't
guess: assets live at `/app/portfolios/:portfolioId/assets/:holdingId`, not
`/holdings/:holdingId` — the AI analysis screen is
`.../assets/:holdingId/analysis`.

## 4. Shadow DOM — just works

Every screen is a native web component (`customElements.define`,
`this.shadow = attachShadow(...)`). Playwright selectors (`page.click`,
`page.fill`, `page.locator`) **pierce open shadow roots automatically** —
no special syntax needed, `'#submit-btn'` or `'.summary'` just work even
though they live inside a component's shadow root.

## 5. Where screenshots go

Save every verification screenshot under a **gitignored** top-level folder,
one subfolder per changeset or spec worked on:

```
verification-screenshots/
  changeset-c18-bilingual-ai-summary/
    01-login.png
    02-analysis-en.png
    03-settings-language-switch.png
    04-analysis-es.png
  spec-d13-whatever-comes-next/
    ...
```

`verification-screenshots/` is in `.gitignore` — these are working
artifacts for the session, not repo content. Name files with a short
numeric prefix + what they show, so a reviewer (or a future session) can
tell the story just from filenames. Delete any throwaway driver script
(`frontend/.playwright-scratch.js`) when done — it's also gitignored, but
no need to leave clutter.

## 6. What "verified" means here

Not just "the page loaded" — drive to the point a user would actually see
the change: fill the form, click the button that triggers the new
behavior, screenshot the result, and for anything language/state-dependent
(like C18's bilingual summary), explicitly toggle the relevant setting and
screenshot *both* states so the diff is visible in the screenshots
themselves, not just asserted in prose.

Check `console --errors`-equivalent too — wire up
`page.on('pageerror', ...)` and `page.on('console', msg => msg.type() ===
'error' && ...)` before navigating, and confirm nothing fired.
