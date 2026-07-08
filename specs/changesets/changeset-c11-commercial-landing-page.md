# Changeset C11 — Commercial Landing Page (Eural / Portfolio IA)

**Status:** Implemented
**Type:** Cross-spec changeset
**Triggered by:** Need to publish a commercial landing page as the public entry point of the site, presenting Portfolio IA as the flagship product of Eural Spain Soft Technology S.L. with clear paths to login and registration.
**Affects implementations of:** Spec D10 (Frontend Architecture), Spec D08 (i18n), Spec D01 (Authentication routes)

---

## 0. How to read this document

This is a **cross-spec changeset**, not a new spec. It defines a new top-level route surface (`/`) that displays a marketing landing page, and moves all existing application routes under the `/app/*` prefix. The application logic, authentication flow, RBAC model, and API contracts are **unchanged**. What changes is:

1. Where the app lives in the URL space (now under `/app/*`).
2. What lives at the root (`/`) — a new landing page component.
3. The visual identity for the landing (Eural brand tokens, distinct from the existing app tokens).

---

## 1. Motivation

The current frontend deploys at `/` and immediately renders the login screen. This is functional but has two gaps:

- **Marketing gap:** the app has no public "front door" for prospective users. Anyone landing on the URL sees a login form without any context about what the product does or who is behind it.
- **Brand gap:** the product Portfolio IA is created by **Eural Spain Soft Technology S.L.**, but the current frontend has no visible presence of the brand. This is a marketing weakness and misses an opportunity to reinforce the corporate identity for the TFM defence.

C11 introduces a **single-page landing** at the root (`/`) presenting Portfolio IA as the product, with Eural mentioned as the creator in the footer. The app is preserved intact, only moved under `/app/*`.

---

## 2. Scope decisions locked with the project owner

- **Landing is the root (`/`)**. The app moves under `/app/*`. E.g. `/login` becomes `/app/login`, `/portfolios` becomes `/app/portfolios`.
- **Focus of the landing: the product** (Portfolio IA). Eural appears in the footer as the creator.
- **Length:** single-page, ~1 viewport of scroll. Hero → 4 features (2×2 grid) → CTA → footer.
- **Visual identity:** the color palette is derived from the real Eural logo — charcoal gray + warm gold + silver + off-white. No blue tones.
- **Product name in the hero:** *"Portfolio IA"* — short, clean.
- **The Eural logo image is used as-is** in both the header (small size) and the footer (larger size). The logo file lives at `frontend/public/assets/eural-logo.png` (to be copied from the source file the project owner has locally at `D:\MSOneDrives\OneDrive - EURAL SPAIN SOFT TECHNOLOGY S.L\Company\logo.png`).
- **CTAs point to the app registration/login routes:** the "Empezar gratis" and "Crear cuenta" buttons link to `/app/register`; the "Iniciar sesión" button links to `/app/login`. These are the existing screens, unchanged.
- **The landing is public** — no auth required, no cookies set on load, no CSRF required.

---

## 3. Move existing application routes under `/app/*`

### What changes

Every existing route in Spec D10 §6.1 gains the `/app` prefix:

| Old route | New route |
|---|---|
| `/login` | `/app/login` |
| `/portfolios` | `/app/portfolios` |
| `/portfolios/new` | `/app/portfolios/new` |
| `/portfolios/:portfolioId` | `/app/portfolios/:portfolioId` |
| `/portfolios/:portfolioId/add-asset` | `/app/portfolios/:portfolioId/add-asset` |
| `/portfolios/:portfolioId/assets/:holdingId` | `/app/portfolios/:portfolioId/assets/:holdingId` |
| `/portfolios/:portfolioId/assets/:holdingId/levels` | `/app/portfolios/:portfolioId/assets/:holdingId/levels` |
| `/portfolios/:portfolioId/assets/:holdingId/analysis` | `/app/portfolios/:portfolioId/assets/:holdingId/analysis` |
| `/portfolios/:portfolioId/assets/:holdingId/history` | `/app/portfolios/:portfolioId/assets/:holdingId/history` |
| `/portfolios/:portfolioId/alerts` | `/app/portfolios/:portfolioId/alerts` |
| `/settings` | `/app/settings` |
| `/settings/change-password` | `/app/settings/change-password` |
| `/admin/users` | `/app/admin/users` |
| `/admin/roles` | `/app/admin/roles` |
| `/admin/cascade-failures` | `/app/admin/cascade-failures` |

### Where in code

- **`frontend/src/router/routes.ts`** — prefix every `path` in the route table with `/app`.
- **`frontend/src/router/router.ts`** — update the router logic so any request to a path starting with `/app/*` is matched against the app routes; any other path (including `/`) is routed to the landing component.
- **`frontend/src/router/router.ts`** — update the post-login redirect logic (currently jumping to `/portfolios/...`) to jump to `/app/portfolios/...`.
- **`frontend/src/api/client.ts`** — update the 401 handler that redirects to `/login` — it now redirects to `/app/login`.
- **Every internal navigation call** (`navigate('/login')`, `navigate('/portfolios')`, etc.) throughout the codebase → prefixed with `/app`. Grep for `navigate\(['"]/[^a]` to find them all.
- **Backend CORS whitelist** — the backend's `FRONTEND_BASE_URL` env variable does not change, since the domain root is the same. The backend does not care about client-side routes.
- **Backend OAuth callback URLs** — Google and Microsoft OAuth callbacks configured in the providers' consoles may need updating if they included specific paths (e.g. `/login/oauth/callback`). If they used the domain root only, no change needed. The project owner should verify in the Google Cloud Console and Azure Entra ID app registration whether the redirect URIs need adjustment; if they do, update to `/app/login/oauth/callback` (or equivalent path used by the backend).

### Why

Per §2, the landing owns the root URL. Every application route must move to `/app/*` so both surfaces coexist without conflicts. This is a mechanical rename with no logic change.

### Acceptance criteria

- Visiting `/` renders the landing (see §4).
- Visiting `/app/login` renders the login screen (previously at `/login`).
- Visiting `/login` (the old URL) redirects to `/app/login` for backward compatibility with any bookmarked link.
- Visiting `/portfolios` (the old URL) redirects to `/app/portfolios/...` for backward compatibility.
- All internal `navigate()` calls throughout the codebase point to `/app/*` paths.
- Post-login redirection lands on `/app/portfolios/new` or `/app/portfolios/:id` as per Spec D02 §10.
- Post-401 redirection lands on `/app/login`.

---

## 4. Add the landing page component

### What changes

Create a new Web Component `pi-landing-page` that renders at the root URL. It is a single-page marketing site with six visual sections in this order:

**4.1 Sticky header**
- Left: the Eural logo image (32px height) followed by the wordmark `"EURAL"` (letter-spacing 0.14em).
- Right: navigation links (`Características`, `Producto`) that scroll to sections; two CTA buttons: `Iniciar sesión` (outlined gold) linking to `/app/login`, and `Crear cuenta` (filled gold) linking to `/app/register`.
- Background: `#2d2d33` (Eural charcoal), 0.5px silver bottom border.

**4.2 Hero section**
- Two silver triangle frames (SVG) mimicking the visual identity of the Eural logo — one open triangle above the content, one inverted below, drawn with `stroke: #c8c8ce`.
- Badge (uppercase, letter-spacing 0.2em): `"GESTIÓN INTELIGENTE DE CARTERAS"` in gold `#c9a961` with matching border.
- Title `"Portfolio IA"` in serif (`Playfair Display` from Google Fonts as web font), font-size 52px, weight 500, white.
- Subtitle in one line, max-width ~520px, color `#c8c8ce`, size 18px: *"Analiza tus inversiones con inteligencia artificial. Indicadores técnicos, análisis fundamental de informes y alertas en un solo lugar."*
- Two CTAs side-by-side: primary (`Empezar gratis` → `/app/register`) filled gold, secondary (`Iniciar sesión` → `/app/login`) outlined silver.
- Trust strip below: `"Sin publicidad · Sin tarjeta · Datos cifrados"` in muted gray.

**4.3 Features section (id `#features`)**
- Slightly darker background `#26262b` to differentiate from hero.
- Section eyebrow: `"CARACTERÍSTICAS"` in gold letter-spacing 0.2em.
- Section title in serif: *"Todo lo que necesitas para decidir con criterio"*.
- 2×2 grid of feature cards, each with:
  - Gold icon (from Tabler outline set, ~24px)
  - Title (weight 500, white)
  - Description (13px, `#a9a9b0`, ~2 lines)
- The four features:
  1. `Indicadores técnicos` — icon `ti-chart-line` — *"Media móvil 200, RSI, MACD, volumen relativo. Actualizados al cierre diario."*
  2. `Análisis IA de informes` — icon `ti-file-analytics` — *"Sube el PDF de un informe trimestral y extrae PER, ROE, deuda y sentimiento automáticamente."*
  3. `Alertas y niveles` — icon `ti-bell` — *"Define precios objetivo de compra y venta. El sistema te avisa cuando se cruzan."*
  4. `Datos privados` — icon `ti-shield-lock` — *"Autenticación cifrada, aislamiento por usuario. Solo tú ves tu cartera."*
- Card style: `#2d2d33` background, 8px border-radius, 0.5px silver border at 12% opacity, 28px padding.

**4.4 CTA section**
- Centered title in serif: *"Empieza a gestionar tu cartera hoy"*.
- Subtitle: *"Crea tu cuenta en menos de un minuto. No pedimos tarjeta."*
- Primary CTA (`Crear cuenta gratis` → `/app/register`).

**4.5 Footer**
- Left: the Eural logo image (24px height) + wordmark, plus one-line tagline *"Desarrollo de software a medida y productos digitales."*
- Right: two link columns:
  - Column `PRODUCTO` (title in gold, letter-spacing 0.2em): links to `#features`, `/app/login`, `/app/register`.
  - Column `EMPRESA`: links to `mailto:contacto@euralsoft.com` and `#privacy` (in-page anchor for a placeholder privacy section — the actual privacy page is out of scope for v1, see §9).
- Copyright bottom row: `"© 2026 Eural Spain Soft Technology S.L. Todos los derechos reservados."`.

**4.6 Design tokens**
- Charcoal background: `#2d2d33` (matches the logo dark gray).
- Alt background (features section): `#26262b`.
- Deepest background (footer): `#1f1f24`.
- Primary text: `#f5f5f5`.
- Secondary text: `#a9a9b0`.
- Muted text: `#7d7d85`.
- Accent (Eural gold): `#c9a961`.
- Silver (borders, frames): `#c8c8ce` at various opacities.
- Body font: `Inter` from Google Fonts (or the system stack already used in Spec D10).
- Display font (H1, H2, section titles): `Playfair Display` from Google Fonts, weight 500.

### Where in code

- **`frontend/public/assets/eural-logo.png`** — the logo file copied from the project owner's local system (source: `D:\MSOneDrives\OneDrive - EURAL SPAIN SOFT TECHNOLOGY S.L\Company\logo.png`). Recommended: also generate an optimized `.webp` version alongside.
- **`frontend/src/screens/landing-page.ts`** — the new component `pi-landing-page`.
- **`frontend/src/styles/landing-tokens.css`** — separate CSS custom properties for the landing page, so the Eural visual identity does not pollute the app's own design tokens (which follow Spec D10 §10). Load only when the landing is active.
- **`frontend/index.html`** — add the Google Fonts `<link>` for `Playfair Display` and `Inter`.
- **`frontend/src/router/routes.ts`** — register `/` → `pi-landing-page`, `auth_required: false`.

### Why

Per §2, the landing is the front door of the site. It must render fast (no JS-heavy interactions), look premium (Eural brand), and clearly funnel the user to registration or login.

### Acceptance criteria

- Visiting `/` renders the landing in under 500ms after HTML arrives.
- The header CTAs correctly navigate to `/app/login` and `/app/register`.
- The Eural logo image loads correctly (visible in both header and footer).
- The Playfair Display font loads and applies to the hero title.
- The landing renders identically in Spanish (default) and English (see §5).
- The design tokens for the landing do not leak into the app's own components (verifiable by inspecting `/app/*` pages — their look must be unchanged).
- On mobile (≤ 640px viewport), the layout adapts:
  - Header: nav links collapse into a hamburger menu (`ti-menu-2` icon) opening a dropdown with the same items.
  - Hero: title font-size drops to 38px, subtitle stays readable.
  - Features grid: switches to single column (2×2 → 1×4).
  - Footer: link columns stack vertically.

---

## 5. Translations (Spec D08)

Add to `frontend/src/i18n/locales/es.json` and `en.json`:

| Key | Spanish | English |
|---|---|---|
| `landing.header.nav.features` | Características | Features |
| `landing.header.nav.product` | Producto | Product |
| `landing.header.cta.login` | Iniciar sesión | Sign in |
| `landing.header.cta.register` | Crear cuenta | Sign up |
| `landing.hero.badge` | GESTIÓN INTELIGENTE DE CARTERAS | INTELLIGENT PORTFOLIO MANAGEMENT |
| `landing.hero.title` | Portfolio IA | Portfolio IA |
| `landing.hero.subtitle` | Analiza tus inversiones con inteligencia artificial. Indicadores técnicos, análisis fundamental de informes y alertas en un solo lugar. | Analyze your investments with artificial intelligence. Technical indicators, fundamental analysis of reports, and alerts in one place. |
| `landing.hero.cta.primary` | Empezar gratis | Start free |
| `landing.hero.cta.secondary` | Iniciar sesión | Sign in |
| `landing.hero.trust` | Sin publicidad · Sin tarjeta · Datos cifrados | No ads · No card · Encrypted data |
| `landing.features.eyebrow` | CARACTERÍSTICAS | FEATURES |
| `landing.features.title` | Todo lo que necesitas para decidir con criterio | Everything you need to decide with judgment |
| `landing.features.technical.title` | Indicadores técnicos | Technical indicators |
| `landing.features.technical.body` | Media móvil 200, RSI, MACD, volumen relativo. Actualizados al cierre diario. | Moving average 200, RSI, MACD, relative volume. Updated at daily close. |
| `landing.features.ai.title` | Análisis IA de informes | AI analysis of reports |
| `landing.features.ai.body` | Sube el PDF de un informe trimestral y extrae PER, ROE, deuda y sentimiento automáticamente. | Upload a quarterly report PDF and extract PER, ROE, debt and sentiment automatically. |
| `landing.features.alerts.title` | Alertas y niveles | Alerts and levels |
| `landing.features.alerts.body` | Define precios objetivo de compra y venta. El sistema te avisa cuando se cruzan. | Define buy and sell target prices. The system notifies you when they are crossed. |
| `landing.features.privacy.title` | Datos privados | Private data |
| `landing.features.privacy.body` | Autenticación cifrada, aislamiento por usuario. Solo tú ves tu cartera. | Encrypted authentication, per-user isolation. Only you see your portfolio. |
| `landing.cta.title` | Empieza a gestionar tu cartera hoy | Start managing your portfolio today |
| `landing.cta.subtitle` | Crea tu cuenta en menos de un minuto. No pedimos tarjeta. | Create your account in less than a minute. No card required. |
| `landing.cta.button` | Crear cuenta gratis | Create free account |
| `landing.footer.company.tagline` | Desarrollo de software a medida y productos digitales. | Custom software development and digital products. |
| `landing.footer.column.product` | PRODUCTO | PRODUCT |
| `landing.footer.column.company` | EMPRESA | COMPANY |
| `landing.footer.link.contact` | Contacto | Contact |
| `landing.footer.link.privacy` | Privacidad | Privacy |
| `landing.footer.copyright` | © 2026 Eural Spain Soft Technology S.L. Todos los derechos reservados. | © 2026 Eural Spain Soft Technology S.L. All rights reserved. |

Run the i18n build-time validator from C06 §3 to confirm no keys are missing.

---

## 6. SEO and metadata

### What changes

Add the following meta tags to `frontend/index.html` for the landing:

```html
<title>Portfolio IA — Gestión inteligente de carteras | Eural</title>
<meta name="description" content="Analiza tus inversiones con IA. Indicadores técnicos, análisis fundamental de informes financieros y alertas de precio en un solo lugar. Producto de Eural Spain Soft Technology S.L.">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="Portfolio IA — Gestión inteligente de carteras">
<meta property="og:description" content="Analiza tus inversiones con IA. Indicadores técnicos, análisis fundamental de informes financieros y alertas de precio.">
<meta property="og:image" content="/assets/eural-logo.png">
<meta property="og:type" content="website">
<link rel="icon" type="image/png" href="/assets/eural-logo.png">
```

For a v1 personal-use MVP these are sufficient. Sitemap generation and structured data (`JSON-LD`) are out of scope.

### Why

The landing is the public entry point. Even with minimal SEO ambition, basic meta tags ensure the page is decently indexed and shares correctly on social networks (Open Graph).

### Acceptance criteria

- The tab title in the browser reads `"Portfolio IA — Gestión inteligente de carteras | Eural"`.
- Sharing the URL on Twitter/LinkedIn/WhatsApp shows the Eural logo and the correct description in the preview card.
- The favicon shows the Eural logo.

---

## 7. Backward compatibility for existing URLs

### What changes

Any request to an old application URL (e.g. `/login`, `/portfolios`, `/settings`) should transparently redirect to the new location under `/app/*`. This protects bookmarks and prevents 404s for anyone who was using the app before this change.

Implementation options:

- **Frontend redirect** (recommended for v1): in the router, before matching any route, check if the path matches a legacy pattern; if yes, `navigate()` to the new `/app/*` equivalent.
- **Nginx rewrite** (also acceptable): add rewrite rules in the Nginx configuration used by the frontend Docker container.

The frontend approach is simpler and does not require Nginx changes. Use it.

### Where in code

- **`frontend/src/router/router.ts`** — add a legacy-path mapping table at the top:

```typescript
const LEGACY_REDIRECTS: Record<string, string> = {
  '/login': '/app/login',
  '/portfolios': '/app/portfolios',
  '/settings': '/app/settings',
  // ...one per top-level legacy path
};
```

Before route matching, check if the current path (or its prefix) is in the map and issue a `navigate()` to the new location.

### Acceptance criteria

- Visiting `/login` immediately navigates to `/app/login` without showing an error page.
- Visiting `/portfolios/some-id` navigates to `/app/portfolios/some-id` preserving the path suffix.
- Direct navigation to `/app/login` works without redirection.

---

## 8. Deployment considerations

### What changes

The frontend Docker image needs to be rebuilt and pushed to GHCR with the new component code and the logo asset included. Then the Azure Container App must pull the new image.

Suggested commands (adapted for the project owner's Windows PowerShell environment):

```powershell
# Copy the logo from OneDrive to the repo (one-time step)
Copy-Item `
  "D:\MSOneDrives\OneDrive - EURAL SPAIN SOFT TECHNOLOGY S.L\Company\logo.png" `
  "D:\SourcesControl\RomerPersonal\TFM_BigSchool\frontend\public\assets\eural-logo.png"

# Rebuild and push (from the repo root)
cd D:\SourcesControl\RomerPersonal\TFM_BigSchool

docker build `
  --tag ghcr.io/romercepeda/tfm-bigschool/frontend:latest `
  --file ./frontend/Dockerfile `
  --build-arg VITE_BACKEND_BASE_URL=https://portfolio-ia-backend.icysand-40c562ef.northeurope.azurecontainerapps.io `
  ./frontend

docker push ghcr.io/romercepeda/tfm-bigschool/frontend:latest

# Force Azure Container App to pull the new image
az containerapp update `
  --name "portfolio-ia-frontend" `
  --resource-group "VisualStudioOnline-D8AAAD9D5321436DBEA800C13A773885" `
  --image "ghcr.io/romercepeda/tfm-bigschool/frontend:latest"
```

No backend changes and no configuration changes in Azure are required.

### Acceptance criteria

- After deployment, visiting `https://portfolio-ia-frontend.icysand-40c562ef.northeurope.azurecontainerapps.io/` renders the landing page.
- Visiting `/app/login` renders the login screen.
- All application flows work as before (login, portfolio creation, analysis, alerts).

---

## 9. Out of scope for v1

- **Privacy policy page.** The footer link to `#privacy` is a placeholder scroll anchor. The actual privacy policy is a legal document that requires separate authoring and is not part of this changeset.
- **Terms of service page.** Same reason.
- **Cookie consent banner.** Since the landing sets no cookies (the app only sets them after login, and the landing does not interact with the backend), no consent banner is legally required in v1. If the app itself ever adds analytics cookies, a banner will need to be added.
- **Contact form.** The footer link is a `mailto:` — a full contact form with backend endpoint is not built.
- **Analytics** (Google Analytics, Plausible, etc.). Not integrated in v1.
- **A/B testing infrastructure.** Not needed at this scale.
- **Multiple language landings via separate URLs** (e.g. `/en/` and `/es/`). The landing uses the same i18n `t()` system as the app — language is selected by the user via the language switcher (a future addition; for v1 the browser language / default is applied per Spec D08).
- **Landing-specific screenshots or product images.** The landing uses icons and text only. Adding product screenshots to the features section is a natural v2 enhancement.
- **Testimonials, pricing table, or FAQ.** Deliberately excluded to keep the landing to a single scroll.
- **Blog or content marketing.** Not part of this scope.
- **Dark/light theme toggle for the landing.** The landing is dark-only, matching the Eural brand identity.

---

## 10. Order of implementation

1. **Step 1 — Copy the Eural logo** to `frontend/public/assets/eural-logo.png` from the project owner's OneDrive.
2. **Step 2 — Add Google Fonts** to `frontend/index.html` for `Playfair Display` and `Inter`.
3. **Step 3 — Move all application routes** under `/app/*` (§3) — this is a mechanical rename with no logic change. Verify the app still works before continuing.
4. **Step 4 — Add legacy redirects** (§7) — protects existing bookmarks.
5. **Step 5 — Create `pi-landing-page` component** (§4) with placeholder translations first, then wire the `t()` calls.
6. **Step 6 — Add all i18n keys** to `es.json` and `en.json` (§5). Run the validator.
7. **Step 7 — Add SEO meta tags** (§6).
8. **Step 8 — Rebuild and deploy** (§8).

Suggested commit sequence:

- `chore(assets): add Eural logo to public assets`
- `chore(fonts): add Playfair Display and Inter from Google Fonts`
- `refactor(router): move application routes under /app prefix`
- `feat(router): add legacy URL redirects for backward compatibility`
- `feat(landing): add pi-landing-page component with Eural branding`
- `feat(i18n): add landing page translations (ES + EN)`
- `chore(seo): add meta tags and favicon for landing page`

---

## 11. What this changeset does not change

- **No backend changes.** All API endpoints, RBAC rules, session cookies, and CSRF flows are untouched.
- **No database schema changes.**
- **No new configuration keys** in Spec 00f.
- **No new environment variables** in Spec 00e.
- **No changes to existing screens or components** under `/app/*` beyond the mechanical route rename.
- **Spec D10 §6.1 route table** is not rewritten — it is superseded by the updated table in §3 of this changeset. Consult this changeset alongside Spec D10 for the current route map.

---

## 12. Rationale

Separating the marketing surface (landing) from the application surface (`/app/*`) is standard practice for SaaS products of any scale, from indie MVPs to enterprise platforms. The two surfaces have fundamentally different audiences (prospective users vs. authenticated users), design goals (conversion vs. task efficiency), and lifecycles (marketing iterates fast; app iterates on functionality). Keeping them under a shared codebase but at distinct URL prefixes captures this separation without duplicating infrastructure.

The visual identity is derived directly from the Eural logo colors rather than inventing new ones. This ensures the landing reinforces the brand at first glance and avoids the common pitfall of "SaaS blue" that looks like every other product. The charcoal + gold + silver palette is distinctive, premium, and appropriate for a fintech-adjacent product.

The single-scroll layout is a deliberate constraint. The project owner requested a "simple, direct" landing — features + CTA + footer. Adding testimonials or pricing tables would be marketing noise for an MVP whose users are known (2–5 personal users). If the product ever expands to a wider audience, adding these sections is trivial.

The `/app/*` prefix (rather than a subdomain like `app.eural.com`) keeps deployment simple — one Azure Container App instance, one Docker image, one SSL certificate. If a full separation is ever needed for scaling or SEO reasons, moving to a subdomain is a configuration change, not a code refactor.
