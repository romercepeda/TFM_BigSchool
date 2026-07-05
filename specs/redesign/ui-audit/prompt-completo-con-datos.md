# Prompt completo para la IA de diseño (con todos los datos incrustados)

**Cómo usar este archivo**: copia y pega TODO el contenido de más abajo (desde "Eres mi diseñador/a...") directamente en el chat de tu IA de diseño. Ya lleva incrustado el informe completo y los 6 archivos de tokens como texto — no hace falta que adjuntes esos archivos por separado.

Lo único que **sí tienes que arrastrar/adjuntar aparte como imágenes** (no se pueden pegar como texto) son estas **10 capturas**, desde `specs/redesign/ui-audit/screenshots/`:

- `dashboard_pastel.png` / `dashboard_dark.png`
- `asset_detail_pastel.png` / `asset_detail_dark.png`
- `indicators_legend_pastel.png` / `indicators_legend_dark.png`
- `portfolios_pastel.png` / `portfolios_dark.png`
- `analysis_pastel.png` / `analysis_dark.png`

---
---

Eres mi diseñador/a UI/UX senior. Te doy a continuación, en texto plano dentro de este mismo mensaje, un informe técnico completo sobre el estado actual de **Portfolio IA** (una app web de gestión de carteras de inversión personales, mobile-first, proyecto de fin de máster, single-user hoy pero con arquitectura multi-usuario) y los 6 archivos de tokens/tema de su sistema visual actual, copiados tal cual del código fuente. Además te adjunto 10 capturas de pantalla reales de la app funcionando (5 pantallas × modo claro/oscuro), con datos reales de una cartera de ejemplo — óbservalas junto con este texto.

**Contexto técnico que debes respetar en cualquier propuesta**: el frontend es TypeScript puro sobre Web Components nativos (Custom Elements + Shadow DOM), sin React/Vue/Angular y sin ninguna librería de UI ni de gráficos — todo el sistema visual se resuelve con custom properties CSS (design tokens) y HTML/CSS tabular. Cualquier propuesta de rediseño tiene que poder implementarse dentro de ese mismo sistema de tokens (o proponer una evolución razonable de él), no asumir un framework distinto ni una librería de componentes de terceros.

**Control de versiones**: todo el trabajo de este rediseño (tokens nuevos, componentes, pantallas) se implementará sobre la rama `NvoDiseño`, creada a partir de `master`. Tú no tocas código ni esa rama — tus mockups serán fieles al sistema de tokens para que el desarrollador los traduzca a Web Components en esa rama.

## Lo que necesito que hagas

1. **Diagnóstico visual y de UX** a partir de las 10 capturas y del informe: identifica problemas de jerarquía visual, densidad de información, consistencia entre pantallas, accesibilidad de contraste (revisa en particular el tema oscuro, cuyas sombras usan el mismo `rgb(0 0 0 / …)` que el modo claro — ver §2.4 del informe) y cualquier inconsistencia que veas entre los 5 temas de color (§2.2).

2. **Prioriza y comenta explícitamente estos hallazgos de deuda de UX ya detectados en el código** (§8 del informe), indicando si el rediseño los resuelve, los esconde o los deja igual:
   - Nombres de indicadores sin traducir + claves i18n sin resolver visibles en la tarjeta de indicador (ver capturas de detalle de activo y guía de indicadores).
   - La pantalla de listado de carteras ("Carteras") no tiene barra de navegación superior — sin acceso a ajustes/logout desde ahí.
   - Dos componentes construidos pero nunca usados en ninguna pantalla (`pi-kpi-strip`, franja de KPIs de cartera; `pi-asset-row`, fila de activo).
   - Los 5 "KPIs de cartera" (CAGR, Drawdown, Sharpe, TWR, Volatilidad) están catalogados y traducidos pero nunca se calculan — no hay ninguna pantalla que hoy muestre esos valores.
   - La pantalla de alertas de cartera no llega a cargar datos reales (siempre vacía).

3. **Propón un sistema de diseño renovado** manteniendo la misma estructura de tokens (colores semánticos, espaciado en escala de 4px, radios, tipografía del sistema) pero mejorando:
   - Jerarquía tipográfica y de color (la escala actual tiene 7 tamaños y 4 pesos — dime si sobra o falta algún escalón).
   - Paleta: puedes proponer ajustes a los 5 temas existentes (Por defecto, Pastel, Oscuro, Ocean, Forest) o consolidar en menos, pero justifica el porqué.
   - Sombras y elevación para que funcionen igual de bien en claro y oscuro.
   - Un tratamiento visual claro para las "zonas" de indicador (Positivo/Neutral/Atención) que sea distinguible sin depender solo del color (por daltonismo).

4. **Rediseña las 5 pantallas del informe** (Dashboard de cartera, Detalle de activo con indicadores, Guía de indicadores, Listado de carteras/navegación, Análisis IA de PDFs) manteniendo exactamente los mismos datos y flujos descritos en las secciones 3, 5 y 6 del informe (no inventes funcionalidad nueva de negocio; sí puedes reorganizar/jerarquizar la información existente). Para la pantalla de Análisis IA, ten en cuenta el flujo completo descrito en §6: subida de PDF, estados de trabajo en curso (cola/procesando/error/timeout), historial de informes con badge de señal, edición inline de fecha/nombre del periodo, y el detalle expandible de métricas.

5. **Componentes reutilizables**: revisa el inventario de §7 (tarjeta de indicador, fila de activo, franja de KPIs, subidor de PDF, formulario de nivel de precio, editor de proveedores) y dime qué componentes deberían rediseñarse como parte de un design system consistente, y si falta algún componente reutilizable que hoy se resuelve con HTML ad-hoc en cada pantalla.

## Formato de entrega que espero

- Un resumen del diagnóstico (máx. 1 página).
- 3 direcciones visuales distintas, cada una en claro y oscuro, aplicadas primero al Dashboard de cartera para poder comparar antes de extender al resto.
- Propuesta de tokens actualizados (puedes darlos como tabla o como CSS, en el mismo formato de custom properties que ya uso).
- Mockups o descripciones detalladas de las 5 pantallas rediseñadas, en claro y oscuro, para la dirección que finalmente elija.
- Una lista priorizada de cambios (qué hacer primero) pensando en que la implementación la hará un desarrollador único trabajando sobre Web Components + CSS custom properties, sin margen para incorporar un framework nuevo.

---

# INFORME TÉCNICO COMPLETO (informe-ui-ux.md)

<!-- ======================= INICIO informe-ui-ux.md ======================= -->

# Informe técnico y visual — Portfolio IA (para rediseño UI/UX)

Generado a partir del código fuente real del repo (`d:\SourcesControl\RomerPersonal\TFM_BigSchool`) y de una sesión en vivo contra el entorno de desarrollo local (Docker: backend + worker + Postgres + Redis, y el frontend en `http://localhost:5173`), usando la cuenta de desarrollo `romer@romer.com` y su cartera real "Cartera Personal". Todas las capturas de este documento son reales, no maquetas.

---

## 1. Stack y estructura

### Frontend: sin framework — Web Components nativos + señales

No es React/Vue/Angular. Es **TypeScript puro sobre Custom Elements (Web Components) con Shadow DOM**, con reactividad mediante `@preact/signals-core`. Build tool: **Vite 5**. Tests: **Vitest** + `@open-wc/testing` + `happy-dom`.

`frontend/package.json`:
```json
{
  "dependencies": {
    "@preact/signals-core": "^1.5.1"
  },
  "devDependencies": {
    "@open-wc/testing": "^4.0.0",
    "@types/node": "^20.0.0",
    "happy-dom": "^20.10.6",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vitest": "^1.6.0"
  }
}
```

No hay ninguna librería de componentes ni framework CSS (nada de Tailwind, MUI, Bootstrap, Bulma...). Confirmado por grep exhaustivo sobre `frontend/src`: cero imports de librerías UI/CSS de terceros.

**Router**: hecho a mano con la History API (`frontend/src/router/router.ts`, ~50 líneas) + tabla de rutas declarativa (`frontend/src/router/routes.ts`).

**Estado**: señales de `@preact/signals-core` en `frontend/src/state/*.ts` (auth, tema, idioma, notificaciones, cartera). Sin Redux/Zustand/Context API — no hacen falta al no haber framework.

**Patrón de componente** (`frontend/src/components/common/base-component.ts`):
- Cada componente extiende `BaseComponent extends HTMLElement`, crea su propio Shadow DOM (`mode: "open"`) en el constructor.
- `connectedCallback()` envuelve el render en un `effect()` de signals: cualquier signal global leída dentro de `render()` dispara automáticamente `this.shadow.innerHTML = render()` + `afterRender()`.
- No hay virtual DOM ni diffing: cada render reemplaza el `innerHTML` completo del shadow root. Los componentes con estado propio (no basado en signals) deben forzar el re-render manualmente tras cada `set` de sus propiedades.
- `afterRender()` es el hook para volver a enganchar listeners (se pierden al reemplazar `innerHTML`).

### Backend (contexto, no es UI pero condiciona los datos)

Python 3.12 + FastAPI + SQLAlchemy + Alembic + Pydantic v2, Celery + Redis para el análisis IA en background, PostgreSQL 16. Todo en Docker Compose (`backend`, `db`, `redis`, `worker`, `frontend`).

### Estructura de carpetas del frontend (resumen)

```
frontend/src/
├── main.ts                    # bootstrap: registra custom elements, aplica tema, monta router
├── api/                       # clientes HTTP tipados por dominio (uno por recurso backend)
│   ├── client.ts  auth.ts  portfolios.ts  holdings.ts
│   ├── indicators.ts  market-data.ts  price-levels.ts
│   ├── analyses.ts  admin.ts  settings.ts  types.ts
├── components/                # componentes reutilizables (Web Components)
│   ├── common/base-component.ts
│   ├── header-bar.ts  kpi-strip.ts  asset-row.ts
│   ├── indicator-card.ts  pdf-uploader.ts  price-level-form.ts
│   └── data-providers-editor.ts
├── screens/                   # una pantalla = una ruta = un custom element
│   ├── login-screen.ts  portfolios-screen.ts  create-portfolio-screen.ts
│   ├── dashboard-screen.ts  add-asset-screen.ts  asset-detail-screen.ts
│   ├── set-levels-screen.ts  analysis-screen.ts  history-screen.ts
│   ├── alerts-screen.ts  indicators-legend-screen.ts
│   ├── settings-screen.ts  change-password-screen.ts
│   └── admin-users-screen.ts  admin-user-detail-screen.ts
│       admin-roles-screen.ts  admin-cascade-failures-screen.ts
│       permission-denied-screen.ts
├── router/                    # routes.ts (tabla) + router.ts (History API a mano)
├── state/                     # signals: auth, tema, idioma, notificaciones, cartera
├── styles/
│   ├── tokens.css             # design tokens base (claro/"default")
│   ├── reset.css  app.css
│   └── themes/                # dark.css  pastel.css  ocean.css  forest.css
├── i18n/                      # es.json / en.json + motor de traducción propio
├── config/app-config.ts       # catálogo de temas (THEMES)
└── utils/format.ts            # formateo de número/fecha/moneda
```

---

## 2. Sistema visual actual

### 2.1 Cómo funciona (arquitectura de temas)

- Todo el sistema son **custom properties CSS** (design tokens), no hay CSS-in-JS ni utility classes.
- `styles/tokens.css` define los valores **base** en `:root` (equivalen al tema "Por defecto").
- Cada tema alternativo (`pastel`, `dark`, `ocean`, `forest`) es un archivo que **sólo sobreescribe los tokens de color** bajo el selector de atributo `[data-theme="nombre"]`; el resto de tokens (espaciado, tipografía, radios, sombras) no cambian entre temas.
- Como las custom properties CSS atraviesan los límites de Shadow DOM, **todos los Web Components heredan el tema automáticamente** sin ninguna lógica adicional — es el mismo motivo por el que no hace falta ningún framework de theming.
- **Cambio de tema en runtime**: 100% cliente, sin llamada al backend.
  - Estado: `frontend/src/state/theme-state.ts` — una signal `currentTheme`, persistida en `localStorage` bajo la clave `pi_theme`.
  - Aplicación: `applyTheme(theme)` hace `document.documentElement.dataset.theme = theme` (o lo borra si es `'default'`).
  - Se aplica una vez al arrancar la app, antes de renderizar nada (`main.ts:44`), para evitar parpadeo del tema por defecto.
  - El selector de tema vive en la pantalla de **Ajustes** (`settings-screen.ts`), aplica el cambio al instante (sin botón "Guardar") y su catálogo (id, etiqueta i18n, colores de swatch para la previsualización) está en `frontend/src/config/app-config.ts`.
  - **Tema por defecto real de la app: `pastel`** (no `default`) — así lo fija `DEFAULT_THEME` en `theme-state.ts`.

### 2.2 Paleta de colores completa (los 5 esquemas)

Todos los temas comparten la misma **estructura semántica de tokens** (fondo primario/secundario/superficie, texto primario/secundario/muted, accent+hover+light, danger, success, warning, border+border-focus). Solo cambian los valores hex.

| Token | Por defecto (`:root`) | Pastel *(tema activo por defecto)* | Oscuro (Catppuccin Mocha) | Ocean | Forest |
|---|---|---|---|---|---|
| `--color-bg-primary` | `#ffffff` | `#faf9ff` | `#1e1e2e` | `#f0f9ff` | `#fafaf5` |
| `--color-bg-secondary` | `#f8fafc` | `#f0ebff` | `#181825` | `#e0f2fe` | `#f0f4e8` |
| `--color-bg-surface` | `#f1f5f9` | `#e4dcff` | `#313244` | `#bae6fd` | `#dfebd0` |
| `--color-text-primary` | `#0f172a` | `#2d2857` | `#cdd6f4` | `#0c4a6e` | `#1a2e1a` |
| `--color-text-secondary` | `#475569` | `#6b669a` | `#a6adc8` | `#0369a1` | `#4a6741` |
| `--color-text-muted` | `#94a3b8` | `#b5b0d4` | `#585b70` | `#7dd3fc` | `#8aab78` |
| `--color-accent` | `#2563eb` | `#8677f0` | `#89b4fa` | `#0284c7` | `#2d7a22` |
| `--color-accent-hover` | `#1d4ed8` | `#7163d8` | `#74c7ec` | `#0369a1` | `#236018` |
| `--color-accent-light` | `#dbeafe` | `#eeebff` | `#1e3a5f` | `#e0f2fe` | `#dff0d8` |
| `--color-danger` | `#dc2626` | `#f0758b` | `#f38ba8` | `#dc2626` | `#c0392b` |
| `--color-danger-light` | `#fee2e2` | `#fde8ef` | `#3b1a23` | `#fee2e2` | `#fde8e8` |
| `--color-success` | `#16a34a` | `#52c49a` | `#a6e3a1` | `#059669` | `#27ae60` |
| `--color-success-light` | `#dcfce7` | `#ddfaee` | `#1a3b1a` | `#d1fae5` | `#d5f5e3` |
| `--color-warning` | `#d97706` | `#f0a870` | `#f9e2af` | `#d97706` | `#d4890e` |
| `--color-warning-light` | `#fef3c7` | `#fef3e2` | `#3b2e0d` | `#fef3c7` | `#fef0c7` |
| `--color-border` | `#e2e8f0` | `#ddd6ff` | `#45475a` | `#7dd3fc` | `#c5d9b0` |
| `--color-border-focus` | `#2563eb` | `#8677f0` | `#89b4fa` | `#0284c7` | `#2d7a22` |

Solo **un** tema es oscuro (`dark`); los otros cuatro (`default`, `pastel`, `ocean`, `forest`) son variaciones de fondo claro con distinto tinte de color. No hay "modo automático" (sincronizado con `prefers-color-scheme` del sistema) — el usuario elige explícitamente uno de los 5 en Ajustes.

### 2.3 Tipografía

```css
--font-family-sans: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-size-xs:   0.75rem;   /* 12px */
--font-size-sm:   0.875rem;  /* 14px */
--font-size-base: 1rem;      /* 16px */
--font-size-lg:   1.125rem;  /* 18px */
--font-size-xl:   1.25rem;   /* 20px */
--font-size-2xl:  1.5rem;    /* 24px */
--font-size-3xl:  1.875rem;  /* 30px */
--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
--font-weight-bold: 700;
--line-height-tight:  1.25;
--line-height-normal: 1.5;
--line-height-relaxed: 1.75;
```

Una única familia (fuentes del sistema, sin webfont cargada) y una escala de 7 tamaños. No hay tipografía secundaria (ej. serif para cifras destacadas) ni tabular-nums a nivel global (se aplica puntualmente vía `font-variant-numeric: tabular-nums` en columnas numéricas de tablas).

### 2.4 Espaciado, radios y sombras

```css
/* Espaciado (escala de 4px) */
--space-1: 4px   --space-2: 8px   --space-3: 12px  --space-4: 16px
--space-5: 20px  --space-6: 24px  --space-8: 32px  --space-10: 40px
--space-12: 48px --space-16: 64px

/* Radios */
--radius-sm: 4px   --radius-md: 8px   --radius-lg: 12px
--radius-xl: 16px  --radius-full: 9999px
--border-width: 1px

/* Sombras */
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);

/* Z-index y layout */
--z-dropdown: 100  --z-modal: 200  --z-toast: 300
--header-height: 56px
--max-content-width: 1200px
```

Estos tokens **no cambian entre temas** (solo el color varía). Las sombras no se ajustan al tema oscuro (siguen siendo `rgb(0 0 0 / ...)`, que se nota menos sobre fondo oscuro — punto a revisar en el rediseño).

---

## 3. Inventario de pantallas

> Nota de mapeo: la app no distingue "Dashboard" de "Detalle de cartera" como pantallas separadas — una **cartera** (`Portfolio`) se resume en `dashboard-screen`, y el siguiente nivel de detalle es el de un **activo/posición** (`Holding`) dentro de ella, en `asset-detail-screen`. La vista de indicadores/métricas "pura" (sin datos de un activo concreto) es `indicators-legend-screen`; los valores reales de indicadores se ven insertados dentro de `asset-detail-screen`.

### 3.1 Dashboard / resumen de cartera — `dashboard-screen.ts`

**Propósito**: cabecera de la cartera (nombre, moneda, estado) + listado de sus posiciones.

**Componentes**: `<pi-header-bar>`. El listado de holdings se pinta con HTML manual — **no reutiliza** `pi-asset-row` (que existe en `components/asset-row.ts` pero no se usa aquí; ver hallazgo en §8).

**Datos**: `getPortfolio(id)` + `listHoldings(id)` (`api/portfolios.ts`, `api/holdings.ts`) → **base de datos interna**. No hay precio de mercado en tiempo real en esta vista, solo precio medio de compra y cantidad.

**Capturas adjuntas**: `dashboard_pastel.png` (claro) / `dashboard_dark.png` (oscuro) — cartera real "Cartera Personal": INTC, TEF, SNDK, IDR, IAG.

### 3.2 Detalle de activo dentro de una cartera — `asset-detail-screen.ts`

**Propósito**: posición completa de un activo — coste, valor de mercado, P/L, lotes de compra, ventas e indicadores técnicos/fundamentales.

**Componentes**: `<pi-header-bar>` + un `<pi-indicator-card>` por cada indicador de scope `asset` (montados vacíos y poblados después vía `_mountIndicatorCards()`).

**Datos** (la pantalla con más mezcla de fuentes de todo el frontend):
- `getHolding()` (`api/holdings.ts`) → **BD interna**: activo, agregados, lotes, ventas.
- `getAssetPrice()` (`api/market-data.ts`) → **proveedor de mercado externo** (TwelveData/Finnhub); en este entorno de desarrollo no hay API key configurada, por eso en las capturas el precio actual sale relleno con un valor cacheado o "n/d" según el momento.
- `listIndicators()` + `getAssetIndicators()` (`api/indicators.ts`) → **BD interna**: catálogo de indicadores + snapshots ya calculados (los técnicos por el job diario, los fundamentales extraídos por IA de los informes PDF).

**Capturas adjuntas**: `asset_detail_pastel.png` (claro) / `asset_detail_dark.png` (oscuro) — activo real: Intel / INTC, 50 unidades a 19,50 USD.

### 3.3 Vista de indicadores / métricas — `indicators-legend-screen.ts`

**Propósito**: guía explicativa de todos los indicadores disponibles (técnicos, fundamentales, KPIs de cartera) y cómo interpretar sus zonas. Solo definiciones/umbrales, sin valores reales de un activo.

**Componentes**: `<pi-header-bar>`.

**Datos**: `listIndicators()` (`api/indicators.ts`) → **BD interna** (catálogo/configuración, incluye `threshold_config` con 6 modelos de zona distintos).

**Capturas adjuntas**: `indicators_legend_pastel.png` (claro) / `indicators_legend_dark.png` (oscuro).

### 3.4 Navegación general — `portfolios-screen.ts` (listado de carteras)

**Propósito**: listado de todas las carteras del usuario (activas y archivadas) — es la puerta de entrada tras iniciar sesión cuando hay más de una cartera.

**Componentes**: ninguno custom — **no incluye `<pi-header-bar>`** (ver hallazgo §8: en esta pantalla no hay forma de cerrar sesión, ir a ajustes o administración sin volver antes a una cartera).

**Datos**: `listPortfolios()`, `updatePortfolio()`, `archivePortfolio()`, `restorePortfolio()`, `deletePortfolio()` (`api/portfolios.ts`) → **BD interna**.

**Capturas adjuntas**: `portfolios_pastel.png` (claro) / `portfolios_dark.png` (oscuro).

### 3.5 Subida y procesamiento de ficheros (Análisis IA) — `analysis-screen.ts`

**Propósito**: subir informes financieros en PDF para que una IA los analice, y consultar el histórico de análisis ya generados para ese activo.

**Componentes**: `<pi-header-bar>` + `<pi-pdf-uploader>` (drag&drop / selector de fichero).

**Datos**: subida real vía `POST /portfolios/:id/holdings/:id/ai-reports` (encola un job); resto vía `api/analyses.ts` → **BD interna**, pero el *contenido* de cada informe (resumen, señal, métricas) lo genera un **proveedor de IA** a partir del PDF (ver §6 completo).

**Capturas adjuntas**: `analysis_pastel.png` (claro) / `analysis_dark.png` (oscuro) — 3 informes reales de Intel ya procesados por Gemini.

### 3.6 Resto de pantallas (resumen breve)

| Pantalla | Propósito | Datos |
|---|---|---|
| `add-asset-screen.ts` | Alta de un activo nuevo (ticker con autocompletado, cantidad, coste, fecha) | Búsqueda de ticker → proveedor externo (`searchAssets`, debounce 300ms); alta → BD interna |
| `create-portfolio-screen.ts` | Crear cartera (nombre + divisa entre 7 fijas) | BD interna |
| `set-levels-screen.ts` | Alertas de precio (por encima/debajo de un nivel) por activo | BD interna; se evalúan contra precios de mercado en el job diario del backend |
| `history-screen.ts` | Histórico tabular de lotes de compra y ventas de un activo | BD interna; sin loading ni estado vacío explícito |
| `alerts-screen.ts` | Alertas disparadas a nivel de cartera | **Incompleta**: `_load()` inicializa la lista vacía y nunca llama a un endpoint real — siempre muestra el estado vacío (ver §8) |
| `settings-screen.ts` | Cuenta, tema, idioma, actualización manual de mercado, editor de proveedores (admin) | Selector de tema 100% cliente; resto BD interna / proveedor de mercado |
| `login-screen.ts` | Login normal o como invitado | BD interna; email precargado con `romer@romer.com` (dato de desarrollo a revisar antes de producción) |
| `admin-*-screen.ts` (4 pantallas) | Gestión de usuarios, roles y fallos de cascada de proveedores de datos | Solo accesibles con permisos concretos (RBAC, ver §4) |

---

## 4. Navegación

### 4.1 Patrón: topbar fija, sin sidebar ni tabs

Toda la navegación se resuelve con:
1. Una **topbar** fija (`<pi-header-bar>`, 56px de alto) presente en casi todas las pantallas — marca, badge de notificaciones pendientes con tooltip, usuario, botón de administración (si hay permiso), ajustes, cerrar sesión.
2. **Botones de acción contextual** dentro de cada pantalla (`Volver`, `Añadir activo`, `Análisis`, `Niveles de precio`, etc.) que llaman a `navigate(path)`.
3. Sin sidebar, sin bottom-tabs, sin breadcrumbs. La jerarquía se recorre linealmente: Carteras → Cartera (Dashboard) → Activo (Detalle) → {Análisis IA | Niveles de precio | Histórico}.

### 4.2 Implementación

Router hecho a mano (`frontend/src/router/router.ts`, History API): `navigate()` hace `pushState` + notifica suscriptores; `replace()` hace `replaceState`. `resolveRoute()` decide qué custom element montar y aplica las guardas de auth/permiso.

### 4.3 Tabla de rutas completa (`frontend/src/router/routes.ts`)

| Ruta | Pantalla | Auth | Permiso requerido |
|---|---|---|---|
| `/login` | `pi-login-screen` | No | — |
| `/indicators/legend` | `pi-indicators-legend-screen` | Sí | — |
| `/portfolios/new` | `pi-create-portfolio-screen` | Sí | — |
| `/portfolios/:portfolioId/add-asset` | `pi-add-asset-screen` | Sí | — |
| `/portfolios/:portfolioId/assets/:holdingId/levels` | `pi-set-levels-screen` | Sí | — |
| `/portfolios/:portfolioId/assets/:holdingId/analysis` | `pi-analysis-screen` | Sí | — |
| `/portfolios/:portfolioId/assets/:holdingId/history` | `pi-history-screen` | Sí | — |
| `/portfolios/:portfolioId/assets/:holdingId` | `pi-asset-detail-screen` | Sí | — |
| `/portfolios/:portfolioId/alerts` | `pi-alerts-screen` | Sí | — |
| `/portfolios/:portfolioId` | `pi-dashboard-screen` | Sí | — |
| `/portfolios` | `pi-portfolios-screen` | Sí | — |
| `/settings` | `pi-settings-screen` | Sí | — |
| `/settings/change-password` | `pi-change-password-screen` | Sí | — |
| `/admin/users/:userId` | `pi-admin-user-detail-screen` | Sí | `user.view_any` |
| `/admin/users` | `pi-admin-users-screen` | Sí | `user.list` |
| `/admin/roles` | `pi-admin-roles-screen` | Sí | `role.list` |
| `/admin/cascade-failures` | `pi-admin-cascade-failures-screen` | Sí | `system.view_audit_log` |

**Reglas de acceso** (`router.ts:resolveRoute`):
- Ruta protegida sin sesión → redirige a `/login` y recuerda la ruta original (`consumeRedirectAfterLogin`) para volver tras el login.
- Usuario con `must_change_password=true` → forzado a `/settings/change-password` sea cual sea la URL tecleada.
- Ruta con permiso no concedido → no redirige (para no filtrar por historial que la ruta existe), renderiza `pi-permission-denied-screen` en su lugar.

**Enrutado post-login** (`login-screen.ts`): 0 carteras → `/portfolios/new`; 1 cartera → directo a su dashboard; 2+ → `/portfolios`.

---

## 5. Indicadores y métricas

### 5.1 Las 3 agrupaciones reales en UI

La única agrupación visual que existe es por **naturaleza del indicador** (`nature`), literalmente estos 3 títulos de sección en la Guía de indicadores:

- **Técnicos de activo** — recalculados a diario por un job programado.
- **Fundamentales de activo** — se rellenan solo cuando se sube y procesa un informe PDF con IA.
- **KPIs de cartera** — catalogados pero **no implementados** (ver más abajo).

Dentro de la ficha de un activo (`asset-detail-screen`), técnicos y fundamentales aparecen mezclados en una única rejilla bajo el epígrafe "Indicadores", sin subdividir.

#### Técnicos de activo

| Nombre en UI | Código | Unidad | Zonas |
|---|---|---|---|
| 200-Day Moving Average | `ma_200` | — | Positivo / Neutral / Atención (banda ±2% sobre el precio) |
| MA50/MA200 Cross | `ma_50_200_cross` | — | Golden Cross (positivo) / Próximo al Cruce (neutral) / Cruce de la Muerte (atención) |
| RSI 14 | `rsi_14` | — | Atención si <30, Neutral 30–40, Positivo 40–70, Neutral 70–80, Atención ≥80 |
| MACD | `macd` | — | Positivo si >0 y subiendo, Atención si <0 y bajando, Neutral si \|valor\|≤0.5 |
| Relative Volume | `rvol` | x | ≥1.5 positivo, 0.8–1.5 neutral, <0.8 atención — **nunca se calcula en producción** (no hay dato de volumen almacenado; el calculador siempre devuelve `None`) |

#### Fundamentales de activo (rellenados por IA)

| Nombre en UI | Código | Unidad | Zonas |
|---|---|---|---|
| P/E Ratio | `per` | — | <15 positivo, 15–25 neutral, ≥25 atención |
| ROE (%) | `roe` | % | ≥15 positivo, 8–15 neutral, <8 atención |
| Debt/EBITDA (x) | `debt_ebitda` | x | <2 positivo, 2–4 neutral, ≥4 atención |
| Revenue Growth YoY (%) | `revenue_growth_yoy` | % | ≥8 positivo, 0–8 neutral, <0 atención |
| Analyst Sentiment | `analyst_sentiment` | — | Alcista (positivo) / Mixto (neutral) / Bajista (atención) |

#### KPIs de cartera — catalogados pero sin datos

| Nombre en UI | Código | Unidad |
|---|---|---|
| CAGR (%) | `cagr` | % |
| Maximum Drawdown (%) | `max_drawdown` | % |
| Sharpe Ratio | `sharpe` | — |
| Total Return / TWR (%) | `twr` | % |
| Volatility (%) | `volatility` | % |

Todos son "solo informativo — sin zonas de alerta" y **sus 5 calculadoras son stubs que siempre devuelven `None`** (comentario del propio backend: *"Actual computation is out of scope for v1"*). Solo se ven sus fichas descriptivas en la Guía; ninguna pantalla muestra un valor real de TWR/CAGR/Drawdown/Volatilidad/Sharpe hoy.

### 5.2 Colores/zonas

- **Positivo** → verde `--color-success` — señal favorable.
- **Neutral** → gris `--color-text-secondary` — observar antes de actuar.
- **Atención** → rojo `--color-danger` — señal de precaución.
- Sin datos suficientes → guion `—`.

### 5.3 Ejemplo real: Intel (INTC) en "Cartera Personal"

Captura directa de la app (ver `asset_detail_pastel.png`), 50 unidades a 19,50 USD:

| Indicador | Valor mostrado | Zona |
|---|---|---|
| 200-Day Moving Average | 60,335 | (sin badge de zona visible en la card) |
| MA50/MA200 Cross | Golden Cross | Positivo (verde) |
| MACD | 5,539 | Neutral |
| RSI 14 | 49,146 | Positivo |
| Relative Volume | 0,947 | Neutral |
| Analyst Sentiment | Bullish | Positivo (verde) |
| Debt/EBITDA | — | sin dato |
| P/E Ratio | — | sin dato (la empresa tiene pérdidas netas) |
| Revenue Growth YoY | 0,07 (7%) | Neutral |
| ROE | -0,132 (-13,2%) | Atención (rojo) |

> **Hallazgo de i18n** (visible directamente en las capturas de detalle de activo y guía de indicadores): los **nombres de los indicadores** ("200-Day Moving Average", "MACD", "Relative Volume", "Analyst Sentiment"...) se muestran **en inglés** aunque el resto de la interfaz está en español, y las etiquetas de zona en la card de indicador salen literalmente como `indicator.zone.positive` / `indicator.zone.neutral` (la clave de traducción sin resolver) en vez de "Positivo"/"Neutral" — sí funciona correctamente en la pantalla de Guía de indicadores, que traduce bien esas mismas zonas. Es un bug de i18n localizado en `indicator-card.ts` a corregir antes o durante el rediseño.

---

## 6. Datos de ficheros (Análisis IA de informes PDF)

### 6.1 Qué se extrae del PDF

El backend envía el PDF entero a un modelo de IA (proveedor configurable) con un prompt (`backend/ai_extraction_prompt.md`) que exige devolver un JSON con este schema (`backend/ai_extraction_schema.json`):

| Campo | Tipo | Descripción |
|---|---|---|
| `asset_match` | boolean | ¿El PDF es realmente del activo indicado? |
| `asset_match_notes` | string\|null | Si no coincide, qué empresa detectó de verdad |
| `report_date` | `YYYY-MM-DD`\|null | Fecha del informe |
| `report_period_name` | string\|null | Etiqueta del periodo (`"Q1 2026"`, `"FY 2025"`...) |
| `metrics.per` / `per_basis` | number\|null / `GAAP`\|`non-GAAP` | PER y su base |
| `metrics.roe` | number\|null | ROE (decimal, 0.15 = 15%) |
| `metrics.debt_ebitda` | number\|null | Deuda/EBITDA |
| `metrics.revenue_growth_yoy` | number\|null | Crecimiento de ingresos interanual |
| `metrics.analyst_sentiment` | `bullish`\|`mixed`\|`bearish`\|null | Síntesis final |
| `metrics.management_tone` / `fundamentals_signal` | idem | Señales intermedias (no llegan al frontend) |
| `executive_summary` | string | 3–5 bullets, cada uno con "•" |
| `global_signal` | `bullish`\|`neutral`\|`bearish`\|null | Señal global del informe |
| `confidence_notes` | string\|null | Calidad de datos / aproximaciones |
| `calculations_detail`, `data_provenance` | objeto\|null | Trazabilidad de cálculos (solo se persisten, no llegan al frontend) |

### 6.2 Cómo se muestra al usuario (`analysis-screen.ts`)

- **Trabajo en curso**: spinner con estado (`en cola` / `procesando`), aviso de reintento si `attempt_count > 1`, error truncado a 120 caracteres si falla, aviso de timeout a los 10 minutos. Polling cada 3s.
- **Informe completado**: badge de color según `global_signal` (verde=alcista, rojo=bajista, ámbar=neutral/otro), resumen ejecutivo en bullets, chips de "indicadores actualizados" (uno por métrica no nula + la señal global), notas de confianza en cursiva.
- **Historial**: tarjetas por informe con fecha y nombre de periodo **editables inline** (con icono de advertencia si la fecha vino de un fallback o el nombre no se detectó, y aviso especial de colisión de fecha si hay 409), proveedor+modelo en texto pequeño, botón expandible "▼ Ver métricas" (carga perezosa del detalle completo), botón "Eliminar informe" con confirmación inline.
- No hay visor del PDF original en pantalla — se guarda en BD como bytes pero no se re-muestra.

### 6.3 Ejemplo real de salida (los 3 informes de Intel visibles en `analysis_pastel.png`)

```
Bajista · Fecha del informe: 2026-03-28
• Q1 2026 revenue increased 7.2% YoY to $13.6B, driven by higher server pricing...
• Company recognized $3.9B non-cash goodwill impairment (Mobileye)...
• Restructuring charges surged to $4.1B in Q1 2026 vs $156M prior year...
gemini · models/gemini-3-flash-preview

Alcista · Fecha del informe: 2026-04-23
• Intel reported Q1 2026 revenue of $13.6 billion, up 7% YoY...
• Non-GAAP net income surged 156% to $1.5 billion ($0.29 EPS)...
gemini · models/gemini-3-flash-preview
```

Métricas extraídas persistidas para uno de estos informes (`extracted_metrics`, subconjunto expuesto al frontend):
```json
{
  "per": null,
  "roe": -0.132,
  "debt_ebitda": null,
  "revenue_growth_yoy": 0.0718,
  "analyst_sentiment": "mixed"
}
```

### 6.4 Proveedores de IA soportados

Tres adaptadores tras una interfaz común `AIProvider`: **Anthropic**, **OpenAI**, **Google Gemini** — seleccionable por config (`backend/config.yaml`). El entorno actual usa **Gemini** (`models/gemini-3-flash-preview`). Cada proveedor lee su API key de una variable de entorno distinta (`AI_ANTHROPIC_API_KEY` / `AI_OPENAI_API_KEY` / `AI_GEMINI_API_KEY`); sin clave, el job falla directo sin reintentos (error de configuración, no transitorio).

---

## 7. Componentes reutilizables

No existe ninguna librería de gráficos (se descartó explícitamente D3/Chart.js/Recharts/Plotly/canvas/SVG manual — grep exhaustivo sin resultados reales). **Toda visualización de datos es HTML/CSS tabular**: `div`/`span` con flexbox, color condicional inline según signo o "zona" semántica, y texto formateado. El componente más parecido a un gráfico es el mini-histórico de `indicator-card` (2 valores anteriores en texto, no un trazado).

| Componente | Qué es | UI |
|---|---|---|
| `pi-header-bar` | Topbar global | Marca, badge de notificaciones con tooltip, usuario, botones admin/ajustes/logout |
| `pi-indicator-card` | Tarjeta de un indicador | Valor coloreado por zona, mini-histórico de 2 snapshots previos, tooltip explicativo con posicionamiento dinámico |
| `pi-asset-row` | Fila de un activo en una lista | Ticker+nombre a la izq., precio medio+cantidad a la der., clicable — **existe pero no se usa** en `dashboard-screen` (que reimplementa la fila a mano) |
| `pi-kpi-strip` | Franja de KPIs de cartera (invertido, valor actual, ganancia/pérdida...) | 5 bloques flex — **no está montado en ninguna pantalla** (huérfano, ver §8) |
| `pi-pdf-uploader` | Zona de subida de PDF | Drag&drop + selector, estados `.uploading`/`.over`, emite `upload-queued` |
| `pi-price-level-form` | Formulario de alerta de precio | Precio objetivo + dirección (above/below) + etiqueta, valida en cliente, emite `level-created` |
| `pi-data-providers-editor` | Editor admin de proveedores de datos de mercado/FX | Listas reordenables por drag&drop nativo (HTML5 DnD, sin librería), indicador de API key configurada, añadir/quitar proveedor |

---

## 8. Hallazgos relevantes para el rediseño (deuda técnica de UX detectada)

1. **Nombres de indicadores sin traducir + claves i18n sin resolver visibles al usuario** (`indicator-card.ts`, ver §5.3) — bug activo, visible en producción tal cual.
2. **`portfolios-screen` no tiene topbar** — es la única pantalla autenticada sin `<pi-header-bar>`; el usuario no puede cerrar sesión ni ir a ajustes desde ahí sin entrar antes a una cartera.
3. **`pi-kpi-strip` es un componente huérfano**: llama a `GET /portfolios/{id}/kpis`, endpoint que **no existe** en el backend, y no está insertado en ninguna pantalla. Es una funcionalidad de KPIs de cartera a medio construir, distinta de los 5 "KPIs de cartera" del catálogo de indicadores (que también son stubs sin datos, §5.1).
4. **`pi-asset-row` tampoco se usa** — `dashboard-screen` reimplementa la fila de holding con HTML propio en vez de reutilizar el componente ya existente.
5. **`alerts-screen` está incompleta**: inicializa la lista de alertas vacía y nunca llama a ningún endpoint — siempre muestra el estado vacío pase lo que pase.
6. **Colores de zona "muertos" en código**: `indicator-card.ts` define colores para `overbought`/`bullish`/`bearish` que el backend nunca produce (solo emite `positive`/`neutral`/`attention`), resto de una versión anterior del modelo de zonas.
7. **Sombras no adaptadas al tema oscuro**: `--shadow-*` sigue usando `rgb(0 0 0 / …)` en todos los temas, con menos contraste visual sobre fondos oscuros.
8. **Sin precio de mercado en tiempo real** en este entorno de desarrollo (no hay API key de proveedor de mercado configurada) — el campo "Precio actual" cae a "n/d" o a un valor cacheado; tenerlo en cuenta al diseñar el estado vacío/error de esa tarjeta.
9. **Email de desarrollo precargado** en `login-screen.ts` (`romer@romer.com`) — a retirar antes de cualquier entorno no local.

<!-- ======================= FIN informe-ui-ux.md ======================= -->

---

# ARCHIVOS DE TOKENS/TEMA (copiados tal cual del código)

### `tokens.css`

```css
/* Design tokens — Portfolio IA (Spec D10 §10.1)
   Breakpoints (not in custom properties — @media can't use them):
   sm: 640px  md: 768px  lg: 1024px  xl: 1280px */

:root {
  /* Colors */
  --color-bg-primary:      #ffffff;
  --color-bg-secondary:    #f8fafc;
  --color-bg-surface:      #f1f5f9;
  --color-text-primary:    #0f172a;
  --color-text-secondary:  #475569;
  --color-text-muted:      #94a3b8;
  --color-accent:          #2563eb;
  --color-accent-hover:    #1d4ed8;
  --color-accent-light:    #dbeafe;
  --color-danger:          #dc2626;
  --color-danger-light:    #fee2e2;
  --color-success:         #16a34a;
  --color-success-light:   #dcfce7;
  --color-warning:         #d97706;
  --color-warning-light:   #fef3c7;
  --color-border:          #e2e8f0;
  --color-border-focus:    #2563eb;

  /* Spacing scale */
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  20px;
  --space-6:  24px;
  --space-8:  32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  /* Typography */
  --font-family-sans: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-size-xs:   0.75rem;
  --font-size-sm:   0.875rem;
  --font-size-base: 1rem;
  --font-size-lg:   1.125rem;
  --font-size-xl:   1.25rem;
  --font-size-2xl:  1.5rem;
  --font-size-3xl:  1.875rem;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
  --line-height-tight:  1.25;
  --line-height-normal: 1.5;
  --line-height-relaxed: 1.75;

  /* Borders & radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;
  --border-width: 1px;

  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);

  /* Z-index */
  --z-dropdown: 100;
  --z-modal:    200;
  --z-toast:    300;

  /* Layout */
  --header-height: 56px;
  --max-content-width: 1200px;
}
```

### `dark.css`

```css
/* Dark theme — Catppuccin Mocha inspired.
   Override only color tokens; all spacing/typography tokens stay from tokens.css. */

[data-theme="dark"] {
  /* Backgrounds */
  --color-bg-primary:   #1e1e2e;
  --color-bg-secondary: #181825;
  --color-bg-surface:   #313244;

  /* Text */
  --color-text-primary:   #cdd6f4;
  --color-text-secondary: #a6adc8;
  --color-text-muted:     #585b70;

  /* Accent */
  --color-accent:       #89b4fa;
  --color-accent-hover: #74c7ec;
  --color-accent-light: #1e3a5f;

  /* Danger */
  --color-danger:       #f38ba8;
  --color-danger-light: #3b1a23;

  /* Success */
  --color-success:       #a6e3a1;
  --color-success-light: #1a3b1a;

  /* Warning */
  --color-warning:       #f9e2af;
  --color-warning-light: #3b2e0d;

  /* Borders */
  --color-border:       #45475a;
  --color-border-focus: #89b4fa;
}
```

### `pastel.css`

```css
/* Pastel theme — soft lavender-violet palette.
   All rules are scoped to [data-theme="pastel"] on <html>, which is set at
   runtime from APP_CONFIG.theme. CSS custom properties cascade through Shadow
   DOM boundaries, so Web Components pick up every override automatically. */

[data-theme="pastel"] {
  /* Backgrounds */
  --color-bg-primary:   #faf9ff;
  --color-bg-secondary: #f0ebff;
  --color-bg-surface:   #e4dcff;

  /* Text */
  --color-text-primary:   #2d2857;
  --color-text-secondary: #6b669a;
  --color-text-muted:     #b5b0d4;

  /* Accent */
  --color-accent:       #8677f0;
  --color-accent-hover: #7163d8;
  --color-accent-light: #eeebff;

  /* Semantic — danger */
  --color-danger:       #f0758b;
  --color-danger-light: #fde8ef;

  /* Semantic — success */
  --color-success:       #52c49a;
  --color-success-light: #ddfaee;

  /* Semantic — warning */
  --color-warning:       #f0a870;
  --color-warning-light: #fef3e2;

  /* Borders */
  --color-border:       #ddd6ff;
  --color-border-focus: #8677f0;
}
```

### `ocean.css`

```css
/* Ocean theme — sky-blue / teal palette. */

[data-theme="ocean"] {
  /* Backgrounds */
  --color-bg-primary:   #f0f9ff;
  --color-bg-secondary: #e0f2fe;
  --color-bg-surface:   #bae6fd;

  /* Text */
  --color-text-primary:   #0c4a6e;
  --color-text-secondary: #0369a1;
  --color-text-muted:     #7dd3fc;

  /* Accent */
  --color-accent:       #0284c7;
  --color-accent-hover: #0369a1;
  --color-accent-light: #e0f2fe;

  /* Danger */
  --color-danger:       #dc2626;
  --color-danger-light: #fee2e2;

  /* Success */
  --color-success:       #059669;
  --color-success-light: #d1fae5;

  /* Warning */
  --color-warning:       #d97706;
  --color-warning-light: #fef3c7;

  /* Borders */
  --color-border:       #7dd3fc;
  --color-border-focus: #0284c7;
}
```

### `forest.css`

```css
/* Forest theme — natural green / earthy palette. */

[data-theme="forest"] {
  /* Backgrounds */
  --color-bg-primary:   #fafaf5;
  --color-bg-secondary: #f0f4e8;
  --color-bg-surface:   #dfebd0;

  /* Text */
  --color-text-primary:   #1a2e1a;
  --color-text-secondary: #4a6741;
  --color-text-muted:     #8aab78;

  /* Accent */
  --color-accent:       #2d7a22;
  --color-accent-hover: #236018;
  --color-accent-light: #dff0d8;

  /* Danger */
  --color-danger:       #c0392b;
  --color-danger-light: #fde8e8;

  /* Success */
  --color-success:       #27ae60;
  --color-success-light: #d5f5e3;

  /* Warning */
  --color-warning:       #d4890e;
  --color-warning-light: #fef0c7;

  /* Borders */
  --color-border:       #c5d9b0;
  --color-border-focus: #2d7a22;
}
```

### `app-config.ts`

```typescript
// Central app configuration.
// To add a new theme:
//   1. Create src/styles/themes/<name>.css with [data-theme="<name>"] { --color-*: ...; }
//   2. Import it in main.ts
//   3. Add the name to the Theme union and an entry to THEMES below.

export type Theme = 'default' | 'pastel' | 'dark' | 'ocean' | 'forest';

export interface ThemeInfo {
  readonly id: Theme;
  readonly labelKey: string;
  // Preview swatch colors (hardcoded — don't use CSS vars here, these render in HTML attributes)
  readonly swatchBg: string;
  readonly swatchAccent: string;
  readonly swatchBorder: string;
}

export const THEMES: readonly ThemeInfo[] = [
  {
    id: 'default',
    labelKey: 'settings.theme.default',
    swatchBg: '#f8fafc', swatchAccent: '#2563eb', swatchBorder: '#e2e8f0',
  },
  {
    id: 'pastel',
    labelKey: 'settings.theme.pastel',
    swatchBg: '#f0ebff', swatchAccent: '#8677f0', swatchBorder: '#ddd6ff',
  },
  {
    id: 'dark',
    labelKey: 'settings.theme.dark',
    swatchBg: '#1e1e2e', swatchAccent: '#89b4fa', swatchBorder: '#45475a',
  },
  {
    id: 'ocean',
    labelKey: 'settings.theme.ocean',
    swatchBg: '#e0f2fe', swatchAccent: '#0284c7', swatchBorder: '#7dd3fc',
  },
  {
    id: 'forest',
    labelKey: 'settings.theme.forest',
    swatchBg: '#f0f4e8', swatchAccent: '#2d7a22', swatchBorder: '#c5d9b0',
  },
];
```

<!-- FIN de datos incrustados. Recuerda adjuntar además las 10 imágenes de screenshots/ como archivos. -->
