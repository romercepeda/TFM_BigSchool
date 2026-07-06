# Checklist de verificación — Changeset C07

Marca cada punto tras aplicar el changeset en la rama `NvoDiseño`.

## Build / arranque
- [ ] `npm run build` compila sin errores de TypeScript.
- [ ] `npm run dev` arranca y la app carga sin errores en consola.
- [ ] No hay warnings nuevos de custom elements no definidos (`pi-kpi-strip`, `pi-asset-row`, `pi-signal-pill`).

## T1 — Tema Terminal
- [ ] Configuración muestra «Terminal» y «Terminal claro» como opciones de tema.
- [ ] Al elegir «Terminal», el fondo es casi-negro (#08090b), acento oro (#c9a45c) y las cifras son monoespaciadas.
- [ ] «Terminal claro» aplica papel neutro (#f5f5f2) manteniendo tipografía mono en cifras.
- [ ] El resto de temas (default, pastel, dark, ocean, forest) siguen funcionando.

## T2 — i18n indicadores
- [ ] Ninguna tarjeta muestra el literal `indicator.zone.positive` (ni neutral/attention).
- [ ] Ningún nombre de indicador aparece en inglés (p. ej. «200-Day Moving Average» → «Media Móvil 200»).
- [ ] La píldora de zona dice «Positivo» / «Neutral» / «Atención».
- [ ] Buscar en el DOM (`document.body.innerText`) que no contenga `indicator.zone.` ni `.name` sin resolver.

## T3 — Tarjeta de indicador
- [ ] Cada tarjeta muestra valor actual en mono + hasta 2 lecturas anteriores con fecha.
- [ ] Técnicos muestran 2 lecturas diarias; fundamentales 1 lectura del informe anterior.
- [ ] La zona se distingue en escala de grises (glifo ▲ ● ▼ visible, no solo color).
- [ ] Si un indicador no tiene histórico, el pie no muestra datos ficticios (queda oculto o «Sin lecturas anteriores»).

## T4 — Franja de KPIs
- [ ] El Dashboard muestra la franja con TWR, CAGR, Máxima caída, Volatilidad, Ratio Sharpe.
- [ ] Cada KPI muestra «—» + «Se calculará al cierre diario» (no valores inventados).

## T5 — Navegación en Carteras
- [ ] La pantalla «Carteras» tiene barra superior.
- [ ] Desde ahí se accede a Configuración (⚙) y a Cerrar sesión.

## T6 — Fila de activo
- [ ] Las posiciones del Dashboard se renderizan con `pi-asset-row`.
- [ ] El componente `pi-asset-row` ya no está sin uso.

## T7 — Análisis IA
- [ ] Se muestran estados de job: en cola, analizando (+ reintento n/3), error, completado.
- [ ] El historial muestra badge de señal (Alcista/Neutral/Bajista).
- [ ] Fecha y nombre del periodo son editables inline.
- [ ] El detalle de métricas se expande/colapsa (PER, ROE, D/EBITDA, Ing. YoY, Sentimiento).

## Accesibilidad / contraste
- [ ] Texto secundario legible en oscuro (contraste AA sobre #08090b).
- [ ] Badges de zona con contraste suficiente en ambos modos.
- [ ] Las sombras se ven correctas en oscuro (borde/realce, no cajas negras invisibles).

## Regresión
- [ ] Añadir activo, añadir compra, renombrar/archivar cartera siguen funcionando.
- [ ] Subida de PDF y refresco de indicadores no se han roto.
