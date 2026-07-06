# Changeset C07 — Rediseño visual «Terminal Premium» + saneamiento de UX

- **ID:** C07
- **Rama:** `NvoDiseño` (creada desde `master`). No trabajar sobre `master`.
- **Tipo:** Rediseño de sistema visual + correcciones de deuda de UX (§8 del informe).
- **Alcance frontend:** TypeScript + Web Components nativos (Custom Elements + Shadow DOM). Sistema visual 100 % en CSS custom properties. **Sin** frameworks ni librerías de UI/gráficos nuevos.
- **Archivos de apoyo (esta carpeta):** `specs/changesets/changeset-c07-files/`
  - `assets/terminal.css` — tema nuevo, listo para copiar a `frontend/src/styles/themes/`.
  - `assets/i18n-additions.es.json` — claves i18n a fusionar en `es.json` (y replicar en `en.json`).
  - `PROMPT-VSCODE.md` — prompt para la IA de VS Code.
  - `verification-checklist.md` — checklist de comprobación manual.

---

## 1. Objetivo

Adoptar la dirección visual **1c «Terminal Premium»** (casi-negro + oro discreto, tipografía de display Space Grotesk, cifras monoespaciadas JetBrains Mono, alta densidad tabular) como nuevo tema principal, y de paso resolver la deuda de UX ya detectada en el código. El rediseño **no introduce funcionalidad de negocio nueva**: reorganiza y jerarquiza información existente y activa componentes ya construidos pero sin usar.

## 2. Resultado esperado (Definition of Done)

1. Existe un tema `terminal` (oscuro, principal) y `terminal-light` (claro) seleccionables desde Configuración.
2. Las tarjetas de indicador muestran **nombre traducido** y **etiqueta de zona traducida** (nunca `indicator.zone.positive` ni nombres en inglés).
3. Cada indicador muestra su **valor actual + hasta 2 lecturas anteriores con fecha** (histórico).
4. La zona del indicador es distinguible **sin depender solo del color** (glifo ▲ ● ▼ + etiqueta).
5. La pantalla **Carteras** tiene barra de navegación con acceso a Configuración y Cerrar sesión.
6. La franja de **KPIs de cartera** (`pi-kpi-strip`) se muestra en el Dashboard, con estado honesto «—/Se calculará al cierre» para los KPIs aún no calculados (TWR, CAGR, Drawdown, Volatilidad, Sharpe).
7. Las **sombras** funcionan en claro y oscuro (tokens `--elevation-*`), sin `rgb(0 0 0/…)` fijo en oscuro (§2.4).
8. `npm run build` (o el script equivalente) compila sin errores de tipos; la app arranca y las 5 pantallas renderizan.

> Referencia visual: mockup `Dashboard - 3 Direcciones.dc.html`, turno 1c (dashboard claro/oscuro) y turno 2a–2d (detalle de activo, guía de indicadores, carteras, análisis IA).

---

## 3. Tokens de diseño

### 3.1 Tokens NUEVOS en `frontend/src/styles/tokens.css` (`:root`)
Comunes a todos los temas. Ver bloque `:root` documentado en `assets/terminal.css`.

| Token | Valor por defecto (tema claro) | Propósito |
|---|---|---|
| `--font-family-display` | `'Space Grotesk', system-ui, sans-serif` | Títulos / UI |
| `--font-family-mono` | `'JetBrains Mono', ui-monospace, monospace` | Cifras y datos tabulares |
| `--elevation-1/2/3` | mapea a `--shadow-sm/md/lg` | Elevación tokenizada por tema |
| `--zone-positive` / `-bg` / `-border` / `-glyph` | deriva de `--color-success`; glifo `▲` | Zona positiva |
| `--zone-neutral` / `-bg` / `-border` / `-glyph` | deriva de `--color-warning`; glifo `●` | Zona neutral |
| `--zone-attention` / `-bg` / `-border` / `-glyph` | deriva de `--color-danger`; glifo `▼` | Zona atención |

### 3.2 Tema nuevo `frontend/src/styles/themes/terminal.css`
Copiar `assets/terminal.css` tal cual. Define `[data-theme="terminal"]` (oscuro) y `[data-theme="terminal-light"]` (claro). Sigue el patrón de `dark.css`/`ocean.css`: solo sobrescribe tokens de color + elevación + zonas; hereda espaciado y escala tipográfica de `tokens.css`.

### 3.3 Fuentes
Añadir en `index.html` (`<head>`), antes de los estilos:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```
(Alternativa self-hosted con `@font-face` si no se quiere depender de la CDN.)

### 3.4 Registro del tema
En `frontend/src/config/app-config.ts` añadir `terminal` y `terminal-light` a la lista de temas, junto a los existentes (default, pastel, dark, ocean, forest). En `es.json`/`en.json` añadir sus etiquetas (`settings.theme.terminal`, `settings.theme.terminal_light`). `theme-state.ts` no necesita cambios de lógica si ya itera la lista de `app-config`.

---

## 4. Tareas por archivo

> Orden recomendado: 4.1 → 4.2 → 4.3 → 4.4 → 4.5 → 4.6 → 4.7. Cada tarea es autocontenida y verificable.

### T1 — Tokens y tema  *(fundacional)*
- **Archivos:** `styles/tokens.css`, `styles/themes/terminal.css` (nuevo), `index.html`, `config/app-config.ts`, `i18n/locales/es.json`, `i18n/locales/en.json`.
- Añadir tokens §3.1, copiar tema §3.2, cargar fuentes §3.3, registrar tema §3.4.
- **AC:** al seleccionar «Terminal» en Configuración, toda la app cambia a casi-negro + oro y las cifras pasan a monoespaciadas.

### T2 — i18n: nombres y zonas de indicador  *(FIX §8)*
- **Archivos:** `i18n/locales/es.json` (+ `en.json`), y el componente que renderiza la tarjeta (`components/indicator-card.ts`).
- Fusionar `assets/i18n-additions.es.json`.
- En `indicator-card.ts`: renderizar el nombre con `t(indicator.name_key)` y la zona con `t('zone.' + zone)` — **no** `t('indicator.zone.' + zone)` (esa clave solo existe como `.meaning`). El texto `indicator.zone.positive` no debe aparecer nunca en pantalla.
- **AC:** las tarjetas muestran «Media Móvil 200», «RSI (14)»… y la píldora dice «Positivo/Neutral/Atención».

### T3 — Tarjeta de indicador: zona accesible + histórico  *(rediseño componente)*
- **Archivo:** `components/indicator-card.ts`.
- Píldora de señal con **glifo + color + etiqueta** usando los tokens `--zone-*` (patrón CSS en la nota 5 de `assets/terminal.css`). Atributo `data-zone="positive|neutral|attention|unknown"`.
- Añadir pie de **histórico**: renderizar `value_current` + hasta 2 entradas de `history` (`{date,value}`), en `--font-family-mono`, color `--color-text-secondary`, con la fecha en `--color-text-muted`. Técnicos → 2 lecturas diarias; fundamentales → 1 lectura del informe IA anterior. Si no hay histórico, mostrar `indicator.history.empty`.
  - **Contrato de datos:** el histórico ya debe venir del backend/estado; si el DTO de indicador no incluye `history[]`, exponerlo (ver nota T3-data). No inventar valores en el front.
- Cifras del valor con `font-family:var(--font-family-mono); font-variant-numeric:tabular-nums`.
- **AC:** cada tarjeta muestra valor actual y sus lecturas anteriores con fecha; la zona se entiende en escala de grises (glifo).
- **Nota T3-data:** si `history` no existe aún en el DTO (`api/types.ts`), añadir el campo opcional `history?: {date: string; value: string}[]` y poblarlo desde el endpoint de indicadores. Si el backend todavía no lo entrega, dejar el pie oculto tras `if (indicator.history?.length)` — **sin** datos ficticios.

### T4 — Franja de KPIs de cartera  *(activar componente muerto `pi-kpi-strip`)*
- **Archivos:** `components/kpi-strip.ts`, `screens/dashboard-screen.ts`.
- Montar `pi-kpi-strip` en el Dashboard bajo el valor total.
- Mostrar los 5 KPIs (TWR, CAGR, Máxima caída, Volatilidad, Ratio Sharpe). Como aún no se calculan (§8), renderizar valor `screen.dashboard.kpi.pending` («—») + hint `screen.dashboard.kpi.pending_hint`, con estilo atenuado. **No** ocultarlos ni falsear valores.
- **AC:** el Dashboard muestra la franja de KPIs con «—» y el aviso «Se calculará al cierre diario».

### T5 — Barra de navegación en Carteras  *(FIX §8)*
- **Archivos:** `screens/portfolios-screen.ts`, `components/header-bar.ts`.
- Renderizar `pi-header-bar` (o el componente de nav existente) en la pantalla de listado de carteras, con acceso a Configuración (`⚙`) y Cerrar sesión (`nav.logout`).
- **AC:** desde «Carteras» se puede abrir Configuración y cerrar sesión sin volver atrás.

### T6 — Fila de activo  *(activar/estandarizar `pi-asset-row`)*
- **Archivos:** `components/asset-row.ts`, `screens/dashboard-screen.ts`.
- Usar `pi-asset-row` para las posiciones del Dashboard (hoy HTML ad-hoc). Cada fila: símbolo + mercado, nombre, cantidad, píldora de señal (glifo+color) y valor de mercado en mono.
- **AC:** las 5 posiciones se renderizan con `pi-asset-row`; el componente deja de estar sin uso.

### T7 — Análisis IA: estados de trabajo honestos  *(rediseño pantalla)*
- **Archivo:** `screens/analysis-screen.ts`.
- Reflejar los estados reales del job (`queued`/`running`/`retry n/3`/`timeout`/`failed`/`succeeded`) con las claves i18n `analysis.processing.*` y `screen.ai_report.status.*` ya existentes.
- Historial con badge de señal global (Alcista/Neutral/Bajista), edición inline de fecha/nombre y detalle de métricas expandible (PER, ROE, D/EBITDA, Ing. YoY, Sentimiento) + notas de confianza.
- **AC:** la pantalla muestra los estados del pipeline y el historial expandible tal como en el mockup 2d. (La carga de datos reales de alertas queda fuera de C07 — ver §6.)

---

## 5. Componentes del design system (resumen §7 del informe)

| Componente | Acción C07 |
|---|---|
| `pi-indicator-card` | Rediseñar: zona accesible (glifo+color), histórico, cifras mono (T2, T3) |
| `pi-asset-row` | Activar y estandarizar (T6) |
| `pi-kpi-strip` | Activar con estado ghost (T4) |
| `pi-header-bar` | Reutilizar en Carteras (T5) |
| `pi-pdf-uploader` | Ajustar a estilo terminal (T7) |
| `pi-price-level-form` / `pi-provider-editor` | Solo re-tematizado por tokens (sin cambios estructurales) |
| **Nuevo sugerido** `pi-signal-pill` | Extraer la píldora de zona (glifo+color+label) a un componente reutilizable; hoy se repite ad-hoc en tarjeta, fila y análisis |

---

## 6. Fuera de alcance (NO hacer en C07)

- Cálculo real de los KPIs de cartera (TWR/CAGR/…): C07 solo muestra el estado pendiente.
- Carga de datos reales en la pantalla de **alertas de cartera** (§8): sigue vacía; se aborda en un changeset posterior.
- Cambios de backend salvo el campo `history[]` del DTO de indicador (T3-data), y solo si no existe ya.

---

## 7. Verificación

Ver `verification-checklist.md`. Resumen:
1. `npm install` (por si cambian dependencias — no debería) y `npm run build` → sin errores TS.
2. `npm run dev` → arrancar app.
3. Configuración → Tema → «Terminal»: la app cambia a oscuro terminal; repetir con «Terminal claro».
4. Recorrer las 5 pantallas y validar cada AC (T1–T7).
5. Buscar en el DOM que **no** aparezca el literal `indicator.zone.` ni nombres de indicador en inglés.
6. Comprobar contraste AA en oscuro (texto secundario `#99a0ab` sobre `#08090b`, badges de zona).

## 8. Rollback

Todo el trabajo vive en `NvoDiseño`. Rollback = `git revert` del merge del changeset o descартar la rama. El tema nuevo es aditivo (no elimina temas existentes), por lo que revertir no rompe temas previos.

## 9. Commits sugeridos (uno por tarea)

```
C07-T1  feat(theme): add Terminal Premium theme + design tokens (mono, elevation, zones)
C07-T2  fix(i18n): resolve indicator name/zone keys on indicator card
C07-T3  feat(indicator-card): accessible zone pill + per-indicator history
C07-T4  feat(dashboard): mount portfolio KPI strip with pending state
C07-T5  fix(portfolios): add navigation bar (settings/logout access)
C07-T6  refactor(dashboard): render holdings with pi-asset-row
C07-T7  feat(analysis): honest job states + expandable report history
```
