# Spec D10 — Frontend Architecture & Components

**Status:** Approved
**Type:** Domain capability
**References:** Spec 00a (Coding Conventions), Spec 00b (Security Practices), Spec 00c (Testing Strategy), Spec 00d (Containerization & Deployment), Spec D01 (Authentication), Spec D07 (AI Analysis), Spec D08 (Internationalization)

---

## 1. Purpose

Define the technical architecture of the frontend application: the framework choice (or absence of one), the bundler, the routing mechanism, the reactivity primitive, the component model, how the frontend communicates with the backend, the structure of the source code, and the testing approach for the frontend layer.

The frontend implements the 11 screens defined in the functional design phase, consumes the API contracts defined by the domain specs (D01–D09), and applies the i18n rules of Spec D08.

This spec does **not** define visual design (colors, typography, exact layouts) — that belongs to the design tokens spec and the Figma file. It defines the **technical scaffolding** that any visual design will be built on top of.

---

## 2. Core stack decisions

| Concern | Choice | Why |
|---|---|---|
| Language | TypeScript (`strict: true`) | Per Spec 00a §4. Type safety on every interaction with the backend API. |
| UI primitive | **Web Components** (native, standard HTML elements via `customElements.define`) | W3C standard since 2018, runs natively in every modern browser, no framework lock-in, survives technology cycles. Aligned with the project's portability theme. |
| Reactivity | **`@preact/signals-core`** (~2KB) | Provides `signal()` and `effect()` primitives for automatic DOM updates when state changes. Pure dependency, not a framework — replaces only the manual subscription bookkeeping. |
| Bundler / dev server | **Vite** | Industry-standard modern bundler. Native TypeScript support, fast hot module reload, no configuration needed for our case. |
| Routing | **History API** (hand-written, ~50 lines) | Eleven screens is small enough to not justify a library. Direct browser API, full control. |
| HTTP client | **`fetch`** (browser-native) + a thin wrapper | No external HTTP library needed. The wrapper centralizes auth headers, error normalization, and JSON handling. |
| Test runner | **Vitest** + `@open-wc/testing` for Web Components | Spec 00c §2 already calls these out. Vitest pairs naturally with Vite. |
| Style approach | Plain CSS with CSS custom properties (`--variable-name`) | No CSS-in-JS, no preprocessor. Custom properties give themability without tooling. Component-scoped styles live inside the component's Shadow DOM. |

No additional UI library, no component library (no Material, no Bootstrap, no Tailwind). The frontend is fully owned code with one runtime dependency (`@preact/signals-core`) and one build-time toolchain (Vite + Vitest).

---

## 3. Project structure

```
frontend/
├── public/
│   └── index.html                    # The single HTML entry point
├── src/
│   ├── main.ts                       # App bootstrap: router, root component
│   ├── api/
│   │   ├── client.ts                 # Fetch wrapper (auth, errors, JSON)
│   │   ├── auth.ts                   # Login/logout endpoint calls
│   │   ├── portfolios.ts             # Portfolio endpoints
│   │   ├── holdings.ts               # Asset/lot/sale endpoints
│   │   ├── indicators.ts             # Indicator catalog + snapshots
│   │   ├── price-levels.ts           # Price levels + alerts
│   │   ├── analyses.ts               # AI analysis upload, polling
│   │   └── types.ts                  # Shared TypeScript types mirroring backend models
│   ├── state/
│   │   ├── auth-state.ts             # Current user signal
│   │   ├── portfolio-state.ts        # Active portfolio signal
│   │   ├── notification-state.ts     # Header notifications (D07 jobs)
│   │   └── language-state.ts         # Current language signal
│   ├── router/
│   │   ├── router.ts                 # History API wrapper
│   │   └── routes.ts                 # Route table (path → screen)
│   ├── i18n/
│   │   ├── i18n.ts                   # Loader, t() function, Intl wrappers
│   │   └── locales/
│   │       ├── es.json
│   │       └── en.json
│   ├── components/
│   │   ├── common/                   # Shared atoms (button, input, modal, badge)
│   │   ├── kpi-strip.ts              # Portfolio KPI strip
│   │   ├── asset-row.ts              # Asset list row
│   │   ├── indicator-card.ts         # Indicator display with history
│   │   ├── price-level-form.ts       # Define / edit price level
│   │   ├── pdf-uploader.ts           # PDF drag-and-drop
│   │   └── header-bar.ts             # App header with notifications
│   ├── screens/
│   │   ├── login-screen.ts           # Screen 1
│   │   ├── portfolios-screen.ts      # Screen 2
│   │   ├── create-portfolio-screen.ts # Screen 3
│   │   ├── dashboard-screen.ts       # Screen 4
│   │   ├── add-asset-screen.ts       # Screen 5
│   │   ├── asset-detail-screen.ts    # Screen 6
│   │   ├── set-levels-screen.ts      # Screen 7
│   │   ├── analysis-screen.ts        # Screen 8
│   │   ├── history-screen.ts         # Screen 9
│   │   ├── alerts-screen.ts          # Screen 10
│   │   └── settings-screen.ts        # Screen 11
│   ├── styles/
│   │   ├── tokens.css                # Design tokens (colors, spacing, type) as CSS custom properties
│   │   └── reset.css                 # Minimal CSS reset
│   └── utils/
│       ├── format.ts                 # Wrappers over Intl for dates/numbers (Spec D08 §7)
│       └── validation.ts             # Form validation helpers
├── tests/
│   └── (mirrors src/ structure)
├── package.json
├── tsconfig.json
├── vite.config.ts
└── vitest.config.ts
```

Per Spec 00a §4, filenames are `kebab-case.ts`, classes inside are `PascalCase`, custom-element tags are `kebab-case-with-prefix` (Section 4.2).

---

## 4. Web Components — usage pattern

### 4.1 Base class

Every component extends a small base class (`BaseComponent`) provided locally in `src/components/common/base-component.ts`. The base class:

- Attaches Shadow DOM with mode `open` (so tests can introspect).
- Provides a `render()` method that subclasses override.
- Subscribes the component to any signal accessed inside `render()` via a single `effect()`, so the DOM re-renders automatically whenever those signals change.
- Disposes the effect on `disconnectedCallback`.

The base class is ~50 lines of code. It is **not** a framework — it is a thin helper that wires Web Components and signals together. The implementer is free to bypass it if a component needs different behavior; nothing depends on its existence except convention.

### 4.2 Custom element naming

All custom elements are prefixed with `pi-` (Portfolio IA):

- `<pi-login-screen>`
- `<pi-dashboard-screen>`
- `<pi-asset-row>`
- `<pi-kpi-strip>`
- `<pi-indicator-card>`
- `<pi-price-level-form>`
- `<pi-pdf-uploader>`
- `<pi-header-bar>`

The prefix is required by the HTML standard (custom element tags must contain a hyphen) and gives a clear visual signature in the DOM that distinguishes our components from native elements.

### 4.3 Composition over inheritance

Screens compose components, components compose smaller components. No deep class hierarchies. Communication between components is done in this order of preference:

1. **Attributes / properties** (parent → child): the standard Web Components pattern. Parents set attributes on children when they need them to display something specific.
2. **Custom events** (child → parent): children dispatch `CustomEvent` instances; parents listen. Standard DOM pattern.
3. **Shared signals from `src/state/`** (cross-cutting): when state is genuinely global (the current user, the active portfolio, the current language), components read directly from the relevant signal in `src/state/`. This is what reactivity is for.

Avoid prop-drilling through more than two component layers. If something needs to cross three layers, it belongs in `src/state/`.

---

## 5. Reactivity model

`@preact/signals-core` is the only reactivity primitive used. Two main APIs:

- `signal(initialValue)` creates a reactive container. Reading `.value` from inside an `effect()` subscribes the effect to changes.
- `effect(fn)` runs `fn` once and re-runs it whenever any signal accessed inside changes.

Global signals live in `src/state/` (one file per concern, exporting one or more signals). For example, `src/state/auth-state.ts` exports `currentUser` (a `signal<User | null>`). Any component that wants to react to login/logout simply reads `currentUser.value` inside its `render()` method, and the base component's `effect()` wiring handles the re-render automatically.

**No alternative reactivity primitives** (no MobX, no Redux, no Vuex, no Pinia). One way to do reactive state.

The implementer should keep signals **small and granular**. A monolithic "app state signal" defeats the point — every component would re-render on every change. Instead: one signal per logically independent piece of state.

---

## 6. Routing

The router is a hand-written module of ~50 lines in `src/router/router.ts`. Responsibilities:

- Listen for `popstate` events (back/forward buttons).
- Expose a `navigate(path)` function that calls `history.pushState` and triggers re-render.
- Match the current `location.pathname` against the route table in `src/router/routes.ts`.
- Pass URL parameters (e.g. `:portfolio_id`) as properties to the matched screen component.

### 6.1 Route table

| Path | Screen component | Auth required |
|---|---|---|
| `/login` | `pi-login-screen` | No |
| `/portfolios` | `pi-portfolios-screen` | Yes |
| `/portfolios/new` | `pi-create-portfolio-screen` | Yes |
| `/portfolios/:portfolioId` | `pi-dashboard-screen` | Yes |
| `/portfolios/:portfolioId/add-asset` | `pi-add-asset-screen` | Yes |
| `/portfolios/:portfolioId/assets/:holdingId` | `pi-asset-detail-screen` | Yes |
| `/portfolios/:portfolioId/assets/:holdingId/levels` | `pi-set-levels-screen` | Yes |
| `/portfolios/:portfolioId/assets/:holdingId/analysis` | `pi-analysis-screen` | Yes |
| `/portfolios/:portfolioId/assets/:holdingId/history` | `pi-history-screen` | Yes |
| `/portfolios/:portfolioId/alerts` | `pi-alerts-screen` | Yes |
| `/settings` | `pi-settings-screen` | Yes |

### 6.2 Authentication guard

The router checks `currentUser.value` from `src/state/auth-state.ts` for routes marked "auth required." If null, it navigates to `/login` and stores the original requested path to redirect back after successful authentication.

### 6.3 Post-login redirect

Per Spec D01 §6 step 8 and Spec D02 §10 (corrected by Changeset C21), after successful login the router always redirects to `/app/portfolios` — regardless of how many active portfolios the user has, including 0 (the list screen's empty state carries its own "Create portfolio" CTA). This replaced the original count-based rule (2+ → `/portfolios`, 1 → straight to `/portfolios/:id`, 0 → `/portfolios/new`), which made the landing screen unpredictable.

A pending deep-link redirect (the user was bounced to `/app/login` from a protected URL) still takes priority over this default when one is set.

---

## 7. API client

### 7.1 Wrapper (`src/api/client.ts`)

A thin wrapper around `fetch` that centralizes:

- **Base URL**: read from the `BACKEND_BASE_URL` environment variable (passed in at build time by Vite via `import.meta.env.VITE_BACKEND_BASE_URL`).
- **JWT inclusion**: reads the session token from the httpOnly cookie set by the backend on login (per Spec 00b §2). Since httpOnly cookies are not readable from JS, this is handled by browser-managed credentials — the wrapper just sets `credentials: 'include'` on every request.
- **`Accept-Language` header**: set automatically to the current language from `language-state.ts`, so the backend can use it for server-rendered strings per Spec D08 §5.2.
- **Error normalization**: every non-2xx response is parsed into a `ApiError` type with `status`, `code`, `message`, and `details` fields, and re-thrown as a typed exception.
- **Automatic redirect to login on 401**: a 401 response triggers `navigate('/login')` and clears local auth state. The component that initiated the call still sees the error.

### 7.2 Per-resource modules

Each file under `src/api/` (e.g. `portfolios.ts`) exports one async function per backend endpoint. Functions are typed: parameters and return types match the backend's JSON shape exactly. Backend types live in `src/api/types.ts` and are kept in sync manually with the backend's Pydantic models (no automatic generation in v1; see §13).

### 7.3 No global state in API modules

API modules are stateless: they call the backend and return. They do not write to signals directly. Components and screens are responsible for invoking API functions and updating the relevant signals with the results.

---

## 8. Communication with the AI analysis pipeline (D07)

The header notification system specified in D07 §10 is implemented as follows:

- A single component `pi-header-bar` is mounted at the top of every authenticated screen.
- It owns a signal `pendingNotifications` in `src/state/notification-state.ts`.
- It polls the backend's notifications endpoint at the interval specified by `ai.notifications.poll_interval_seconds` (the backend exposes the interval in the auth response).
- New `succeeded` / `failed` entries trigger a visual update (badge with count, dropdown of recent jobs).
- The user clicks a notification to navigate to the relevant asset (Spec D07 §10).

The polling logic stops when the user logs out and restarts when they log in.

---

## 9. Internationalization integration (D08)

Per Spec D08 §5.1, the frontend loads a single locale JSON file based on `currentLanguage.value` from `language-state.ts`. The `t(key, params)` function in `src/i18n/i18n.ts` does:

1. Look up the key in the loaded bundle.
2. If found, interpolate `{name}` placeholders with the provided `params`.
3. If not found, fall back to the default-language bundle.
4. If still not found, return the key itself (a visible bug signal, per Spec D08 §5.5).

Components call `t('common.button.save')` directly inside `render()`. Because `currentLanguage` is a signal and `t()` reads it, switching language triggers re-rendering of every component that uses `t()`. No manual subscription needed.

Number and date formatting wrappers (`formatNumber`, `formatDate`, `formatCurrency`) live in `src/utils/format.ts`. They wrap `Intl.NumberFormat` / `Intl.DateTimeFormat` and read `currentLanguage.value` to choose the locale (per Spec D08 §7).

---

## 10. Styling and design tokens

### 10.1 Design tokens

Design tokens (colors, spacing scale, typography scale, border radius, shadow definitions) live in `src/styles/tokens.css` as CSS custom properties on `:root`. Example:

```css
:root {
  --color-bg-primary: #ffffff;
  --color-text-primary: #1a1a1a;
  --color-accent: #2563eb;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 16px;
  --font-family-sans: system-ui, -apple-system, sans-serif;
  --radius-md: 8px;
  /* etc. */
}
```

Concrete values to be decided when the Figma file is built. The spec only mandates **how** they live in code, not the specific values.

### 10.2 Component-scoped styles

Web Components use Shadow DOM, which encapsulates styles. Each component includes its own `<style>` block inside its shadow root. Tokens defined on `:root` cross the Shadow DOM boundary via CSS custom properties — components reference them with `var(--color-accent)`.

This combination means: design tokens are globally consistent, but no component's internal CSS can leak out and break another component.

### 10.3 No CSS framework

No Bootstrap, no Tailwind, no Material. Pure CSS with custom properties. The trade-off (more lines of CSS written by hand) is accepted in exchange for zero dependencies and full control.

### 10.4 Responsive design

Per the functional design, the application is **mobile-first**. Every screen and component is designed to fit a 360px-wide viewport first, and adapts up using `@media` queries for tablets (768px+) and desktops (1024px+).

The breakpoints live in `tokens.css` as documented values (not custom properties — `@media` queries cannot use them) and are referenced consistently:

```css
/* sm: 640px, md: 768px, lg: 1024px, xl: 1280px */
@media (min-width: 768px) { ... }
```

---

## 11. Forms and validation

Form validation happens at two levels:

1. **Client-side, in `src/utils/validation.ts`**: synchronous checks (required fields, length, format, range). Used to give immediate feedback as the user types or submits.
2. **Server-side, on the backend**: the authoritative validation. The frontend always assumes the backend may reject a submission, and the client-side check is purely a UX accelerator.

Backend validation errors come back through the API client as `ApiError` with a typed `details` field that maps field names to error keys. Forms display these inline next to the offending field. Error keys are i18n keys, resolved via `t()`.

---

## 12. Testing

Per Spec 00c §2, the frontend has a light testing footprint focused on **pure utility logic** (formatting, validation, calculation), not UI rendering.

**Vitest** is the test runner. **`@open-wc/testing`** provides helpers for occasional Web Component tests (mounting a component, querying its shadow root). Coverage targets are not enforced for the frontend per Spec 00c §3; the goal is "tests where they prevent real bugs," not a number.

Out of scope for v1: end-to-end browser tests (Playwright, Cypress). Manual exploratory testing on real screens is acceptable for v1 evaluation.

---

## 13. Type sync between frontend and backend

The frontend's `src/api/types.ts` mirrors the backend's Pydantic models manually. The implementer maintains it by hand whenever the backend's API contract changes.

Automatic generation (e.g. via `openapi-typescript` against FastAPI's auto-generated OpenAPI document) is **out of scope for v1**. It is the natural extension point: when keeping the types in sync becomes friction (typically after a dozen endpoints), introducing it is a small additional spec. For v1, manual sync is acceptable because the API surface is small enough.

---

## 14. Build and deployment

Per Spec 00d §3, the frontend is served from its own Docker container with Nginx serving the compiled static files. The build process:

1. `npm install` (CI or local).
2. `npm run build` invokes Vite, which produces `dist/` containing minified, fingerprinted JS/CSS and the rewritten `index.html`.
3. The container's image is built from a multi-stage Dockerfile: a Node stage runs the build, a Nginx stage copies `dist/` to `/usr/share/nginx/html`.

Environment-specific values (the backend URL) are baked into the build at compile time via `VITE_BACKEND_BASE_URL`. A re-deploy is required when this value changes.

Hot module reload in development is automatic via Vite's dev server, running inside the `frontend` container in development mode.

---

## 15. Out of scope for v1

- **SSR / SSG** (server-side rendering or static site generation). The application is a SPA loaded from a single `index.html`.
- **Service Worker / PWA** (installable app, offline support, push notifications). Per Spec D06 §13 and D07 §13.
- **Component documentation / Storybook**. Components are documented by their TypeScript types and inline JSDoc.
- **Automatic OpenAPI type generation**. Manual sync of `src/api/types.ts` is the v1 mechanism (§13).
- **Internationalization runtime libraries** (i18next, FormatJS). Spec D08's `t()` is implemented in <50 lines of hand-written code.
- **CSS preprocessors** (Sass, Less, PostCSS plugins beyond what Vite includes by default).
- **End-to-end testing automation** (Playwright, Cypress). See §12.
- **State persistence in `localStorage`**. The signals in `src/state/` are in-memory only; reload re-fetches from the backend. JWT session persists via the httpOnly cookie owned by the backend.
- **Theme switching** (light/dark mode toggle). Tokens are designed to make this trivial later, but no toggle UI exists in v1.
- **Accessibility audit** beyond using semantic HTML and `aria-*` attributes where natural. A full WCAG audit is deferred.

---

## 16. Cross-spec consistency

| Other spec | Touch point | This spec's role |
|---|---|---|
| 00a §4 | TypeScript conventions | Enforced via ESLint + Prettier configuration in `frontend/`. |
| 00b §2 / §6 | JWT in httpOnly cookie, CORS configuration | API client uses `credentials: 'include'`; CORS is a backend concern but the frontend's `VITE_BACKEND_BASE_URL` must match what the backend allows. |
| 00c | Testing strategy | Vitest setup matches the strategy; coverage target on frontend is intentionally light. |
| 00d §3 | Containerization | `frontend` container, Nginx serving Vite-built static files. |
| D01 §6 | Login flow | Login screen calls the auth API and stores the resulting user in `currentUser` signal. |
| D02 §10 | Post-login routing | Router's redirect logic implements D02's flow. |
| D03–D09 | Endpoint contracts | Each domain spec's API is consumed by exactly one file in `src/api/`. |
| D07 §10 | Header notification polling | Implemented by `pi-header-bar` component. |
| D08 | i18n | `t()` function, `src/i18n/locales/`, `Intl` formatters. |

---

## 17. Rationale

The choice of plain Web Components + Vite + signals + History API is **deliberately conservative on dependencies and progressive on standards**. Web Components are W3C, signals are a primitive that has been adopted by virtually every major framework (React 19's `use`, Vue's `ref`, Svelte 5's `$state`, SolidJS), Vite is the de facto modern bundler, and the History API is the browser's built-in mechanism for SPA routing. The result is a frontend with one runtime dependency (~2KB) that any developer can read and understand in a week, and that does not face a rewrite when React/Vue/Svelte release breaking changes.

The single-prefix custom element convention (`pi-`) makes the DOM scannable and prevents collisions with potential future Web Components libraries. The Shadow DOM encapsulation prevents the style leakage that plagues hand-rolled CSS at scale.

The decision to keep types in manual sync between frontend and backend (rather than automating from day one) is the same trade-off the project has made repeatedly: keep the moving parts small in v1, document the natural extension point, add complexity only when the friction is felt. Generating types from OpenAPI is a 30-minute exercise when the time comes; setting it up speculatively on day one costs more in build complexity than the manual sync costs in v1.

The mobile-first responsive design is consistent with the project owner's original requirement of "use simple en el celular" — designing the small screen first guarantees that the large-screen experience is at worst an upgrade, never a degradation.
