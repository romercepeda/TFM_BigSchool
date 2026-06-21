# Especificación funcional v0.1
## Sistema de gestión de cartera financiera con IA

> Documento vivo de Spec Driven Development. Se versiona a medida que el diseño evoluciona. Esta es la primera versión consolidada, fruto de la fase de diseño funcional.

---

## 1. Visión y objetivo

Aplicación web (mobile-first) de uso personal para gestionar una o varias carteras de inversión (acciones, ETFs, fondos, Bitcoin). Permite registrar activos, seguir indicadores técnicos y fundamentales con su evolución histórica, definir precios objetivo de compra/venta que quedan guardados en el tiempo, y analizar informes financieros mediante IA. Pensada para una persona con pocos conocimientos técnicos, pero con arquitectura preparada para crecer en complejidad y en número de usuarios.

---

## 2. Alcance de la v1 (MVP)

- Usuario único, con arquitectura preparada para multi-usuario.
- **Multi-cartera**: el usuario puede tener varias carteras, cada una con su propia moneda base.
- Tipos de activo soportados: acciones, ETFs, fondos, Bitcoin (acciones USA incluidas desde el inicio).
- Precios de activos: actualización automática vía API + corrección manual.
- Tipos de cambio: actualización automática vía API + corrección manual (mismo patrón que los precios).
- Análisis de informes financieros: subida manual de PDF procesado por IA. Diseño extensible para añadir más fuentes (scraping, feeds automáticos) sin cambiar la interfaz de usuario.
- Multiidioma (i18n) desde el diseño: todos los textos de interfaz, incluido el catálogo de indicadores, viven fuera del código.

---

## 3. Entidades conceptuales (modelo de datos preliminar)

| Entidad | Descripción | Campos clave |
|---|---|---|
| Usuario | Cuenta del sistema | id, email, idioma preferido |
| Cartera | Agrupación de activos con moneda propia | id, usuario_id, nombre, moneda_base |
| Activo | Instrumento financiero | ticker, nombre, tipo (acción/ETF/fondo/cripto), moneda de cotización, mercado |
| Tenencia | Relación cartera-activo | cartera_id, activo_id |
| Lote de compra | Cada compra individual de un activo | tenencia_id, fecha, cantidad, precio_compra, moneda_activo, tipo_cambio_en_fecha, origen_tipo_cambio (auto/manual/corregido) |
| Indicador (catálogo) | Definición configurable de un indicador | id, nombre, descripción, ámbito (cartera/activo), tipo (técnico/fundamental), naturaleza (cuantitativo/cualitativo), rango_positivo, rango_neutro, rango_atención |
| Valor de indicador | Histórico de valores calculados | activo_id (o cartera_id), indicador_id, fecha, valor |
| Nivel de precio | Precio objetivo de compra/venta definido por el usuario | activo_id, fecha, precio_objetivo_compra, precio_objetivo_venta, notas, estado (activo/tocado) |
| Análisis de informe | Resultado de analizar un informe | activo_id, fecha, fuente (pdf_ia / manual / futuro), resumen, señal, métricas_extraídas |

**Nota de diseño**: el catálogo de Indicadores es una tabla de configuración, no código. Añadir, modificar o desactivar un indicador (técnico, fundamental o de cartera) no requiere cambios en la lógica de la aplicación, solo una nueva fila o edición.

---

## 4. Pantallas y flujo de navegación

| # | Pantalla | Propósito | Transiciones principales |
|---|---|---|---|
| 1 | Inicio / Login | Autenticación | → Mis carteras (si hay varias) o Dashboard |
| 2 | Mis carteras | Lista de carteras del usuario, cada una con su moneda base | → Crear cartera / → Dashboard de la cartera seleccionada |
| 3 | Crear cartera | Define nombre y moneda base de una nueva cartera | → Mis carteras |
| 4 | Dashboard de cartera | Vista resumen: KPIs de cartera (TWR, CAGR, Drawdown, Volatilidad, Sharpe) calculados en la moneda base, lista de activos, selector de cartera | → Ficha de activo / → Añadir activo / → Alertas / → Configuración |
| 5 | Añadir activo | Buscar y registrar un activo + su primer lote de compra | → Dashboard |
| 6 | Ficha del activo | Indicadores técnicos y fundamentales con histórico (valor actual + 2 anteriores), mis niveles, lotes de compra con tipo de cambio | → Definir niveles / → Análisis IA / → Historial / → Lotes |
| 7 | Definir niveles de precio | Precio objetivo de compra/venta + notas | → Ficha del activo |
| 8 | Análisis IA de informe | Subida de PDF, extracción de señales y métricas por IA | → Ficha del activo |
| 9 | Historial de análisis | Lista cronológica de análisis y niveles definidos en el pasado | → Ficha del activo |
| 10 | Panel de alertas | Activos cuyo precio ha tocado un nivel objetivo | → Ficha del activo |
| 11 | Configuración | Fuentes de datos, idioma, moneda, exportación | — |

---

## 5. Catálogo de indicadores v1

### 5.1 Indicadores de cartera (calculados en la moneda base de cada cartera)

| Indicador | Qué mide | Fórmula |
|---|---|---|
| Rentabilidad total (TWR) | Rendimiento real eliminando el efecto de aportes/retiros | (Valor final ajustado / Valor inicial ajustado) − 1 |
| Rentabilidad anualizada (CAGR) | Compara inversiones de distinta duración | (VF / VI)^(1/n) − 1 |
| Drawdown máximo | Peor caída sufrida | (Mínimo posterior − Máximo previo) / Máximo previo |
| Volatilidad | Riesgo global de la cartera | Desviación estándar de los rendimientos |
| Ratio rentabilidad/riesgo (Sharpe) | Si el riesgo asumido compensa | (Rentabilidad − tasa libre de riesgo) / Volatilidad |

### 5.2 Indicadores técnicos por activo (actualización frecuente: diaria/semanal)

| Indicador | Qué representa | 🟢 Positivo | 🟡 Neutro | 🔴 Atención | Naturaleza |
|---|---|---|---|---|---|
| MA200 | Tendencia de largo plazo | Precio > MA200 | Precio dentro de ±2% de MA200 | Precio < MA200 (−2% o más) | Cuantitativo |
| Cruce MA50/MA200 | Cambio de tendencia estructural | Golden Cross (MA50 > MA200) | Cruce reciente (<5% diferencia) | Death Cross (MA50 < MA200) | Cuantitativo |
| RSI 14 | Momentum del precio (escala 0-100) | 40-70 | 30-40 o 70-80 | <30 o >80 | Cuantitativo |
| MACD | Confirmación de impulso de tendencia | MACD > 0 y creciente | Cerca de 0 / cruzando señal | MACD < 0 y decreciente | Cuantitativo |
| RVOL (volumen relativo) | Fuerza del movimiento actual | >1.5x | 0.8x - 1.5x | <0.8x | Cuantitativo |

### 5.3 Indicadores fundamentales por activo (actualización trimestral, con informes)

| Indicador | Qué representa | 🟢 Positivo | 🟡 Neutro | 🔴 Atención | Naturaleza |
|---|---|---|---|---|---|
| PER | Años de beneficio para recuperar el precio pagado | < 15 | 15 - 25 | > 25 (o negativo si hay pérdidas) | Cuantitativo |
| ROE | Rentabilidad sobre el patrimonio | > 15% | 8% - 15% | < 8% | Cuantitativo |
| Deuda / EBITDA | Nivel de endeudamiento | < 2x | 2x - 4x | > 4x | Cuantitativo |
| Crecimiento ingresos (YoY) | Crecimiento del negocio | > 8% | 0% - 8% | < 0% | Cuantitativo |
| Sentimiento informes/analistas | Opinión consolidada (IA + consenso) | Mayoría alcista | Mixto / "Mantener" | Mayoría bajista | Cualitativo |

Todos los rangos son configurables desde el catálogo y podrán ajustarse por tipo de activo o sector en futuras versiones.

---

## 6. Modelo de divisas y cálculo de rendimiento

Cada compra de un activo se registra como un **lote** independiente, con su propio precio de compra (en la moneda de cotización del activo) y el tipo de cambio aplicable en esa fecha (capturado automáticamente vía API, con opción de corrección manual).

Fórmulas aplicadas por lote:

- **Coste en moneda base** = cantidad × precio_compra × tipo_cambio_en_fecha_compra
- **Valor actual en moneda base** = cantidad × precio_actual × tipo_cambio_actual
- **Rendimiento del activo** (en su propia moneda) = (precio_actual − precio_compra) / precio_compra
- **Rendimiento en moneda base** = (valor_actual_base − coste_base) / coste_base
- **Efecto del tipo de cambio** = rendimiento_en_moneda_base − rendimiento_del_activo

Los indicadores de cartera (sección 5.1) se calculan agregando todos los lotes de todos los activos de la cartera, ya convertidos a la moneda base de esa cartera.

---

## 7. Alertas y niveles de precio

- Al guardar nuevos niveles de precio objetivo (compra/venta), se crea una **nueva entrada en el historial**; las entradas anteriores no se sobrescriben.
- Una alerta se activa cuando el precio actual cruza el precio objetivo de compra (por debajo) o el precio objetivo de venta (por encima).
- El panel de alertas consolida todas las alertas activas de todos los activos de la cartera.
- v1: sin notificaciones push. La señal visual (badge en Dashboard + panel de alertas) es suficiente para el MVP.

---

## 8. Requisitos no funcionales

- **i18n**: textos de interfaz y catálogo de indicadores externalizados en archivos de traducción.
- **Multi-cartera**: cada cartera con su propia moneda base; sin vista consolidada multi-moneda en v1.
- **Extensibilidad de fuentes IA**: v1 solo PDF manual; el diseño debe permitir añadir nuevas fuentes (web, feeds) sin romper la interfaz existente.
- **Mobile-first**, responsive a escritorio.
- **Arquitectura**: Spec Driven Development, comenzando simple y evolucionando en complejidad de forma incremental.

---

## 9. Fuera de alcance v1 / roadmap futuro

- Notificaciones push (PWA).
- Vista consolidada de varias carteras en distintas monedas.
- Registro público multi-usuario.
- Fuentes adicionales de análisis IA (scraping, feeds automáticos, noticias).
- Indicadores adicionales o ajuste de rangos por sector/tipo de activo.

---

*Próximos pasos sugeridos: modelo de datos detallado, arquitectura técnica (stack, APIs, estructura del proyecto), y wireframes de alta fidelidad en Figma.*
