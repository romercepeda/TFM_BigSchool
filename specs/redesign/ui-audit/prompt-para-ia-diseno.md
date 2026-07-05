# Prompt para IA de diseño — Rediseño UI/UX de Portfolio IA

Copia y pega el bloque de abajo. Adjunta junto al prompt:
- `specs/redesign/ui-audit/informe-ui-ux.md` (el informe completo)
- Las 10 imágenes de `specs/redesign/ui-audit/screenshots/`
- Los 6 archivos de `specs/redesign/ui-audit/tokens/`

---

Eres mi diseñador/a UI/UX senior. Te adjunto un informe técnico completo (`informe-ui-ux.md`) sobre el estado actual de **Portfolio IA**, una app web de gestión de carteras de inversión personales (mobile-first, proyecto de fin de máster, single-user hoy pero con arquitectura multi-usuario), junto con:

- 10 capturas de pantalla reales de la app funcionando (5 pantallas × modo claro/oscuro), con datos reales de una cartera de ejemplo.
- Los 6 archivos de tokens/tema actuales (`tokens.css`, `dark.css`, `pastel.css`, `ocean.css`, `forest.css`, `app-config.ts`), copiados literalmente del código.

**Contexto técnico que debes respetar en cualquier propuesta**: el frontend es TypeScript puro sobre Web Components nativos (Custom Elements + Shadow DOM), sin React/Vue/Angular y sin ninguna librería de UI ni de gráficos — todo el sistema visual se resuelve con custom properties CSS (design tokens) y HTML/CSS tabular. Cualquier propuesta de rediseño tiene que poder implementarse dentro de ese mismo sistema de tokens (o proponer una evolución razonable de él), no asumir un framework distinto ni una librería de componentes de terceros.

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
- Propuesta de tokens actualizados (puedes darlos como tabla o como CSS, en el mismo formato de custom properties que ya uso).
- Mockups o descripciones detalladas de las 5 pantallas rediseñadas, en claro y oscuro.
- Una lista priorizada de cambios (qué hacer primero) pensando en que la implementación la hará un desarrollador único trabajando sobre Web Components + CSS custom properties, sin margen para incorporar un framework nuevo.
