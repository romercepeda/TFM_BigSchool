# TFM BigSchool — Chat 4: Feature D07 Análisis IA con Gemini

## Stack y convenciones rápidas

- **Backend**: FastAPI (Python 3.12) + SQLAlchemy async + PostgreSQL + Alembic + Celery + Redis.
  Hot-reload en Docker (`docker compose up -d`, puerto 8000).
- **Frontend**: Web Components + Vite + TypeScript + Shadow DOM. Sin framework.
  Screens extienden `BaseComponent`; `render()` devuelve HTML string con `<style>` inline;
  `afterRender()` adjunta event listeners. Nunca `onclick` inline.
- **Auth**: cookie `pi_session` + CSRF double-submit. Helpers `get/post/patch/del` en
  `frontend/src/api/client.ts` gestionan `X-CSRF-Token` automáticamente.
- **Router**: `frontend/src/router/routes.ts` — History API, `navigate(path)`.
- **i18n**: `t(key)` con bundles JSON en `frontend/src/i18n/locales/es.json` y `en.json`.
- **CSS**: variables `var(--...)` de `frontend/src/styles/tokens.css`. Nunca colores hardcodeados.
- **Migraciones**: `.\scripts\db.ps1 generate "msg"` + `.\scripts\db.ps1 upgrade`.
  Commitar modelo + migración juntos.
- **Entorno**: Windows 11 — usar **PowerShell** (NO Git Bash, mangla rutas Windows).

---

## Objetivo de esta sesión

Hacer funcionar la feature **D07 (Análisis IA de informes financieros en PDF)** usando
**Gemini como proveedor**. La infraestructura de backend está completamente implementada;
lo que hay que hacer es:

1. **Cambiar config** para activar Gemini (la API key YA está en `.env`).
2. **Corregir el contrato frontend↔backend**: las URLs del cliente API y el tipo `AiReport`
   no coinciden con los endpoints reales del backend (ver sección de bugs conocidos).
3. **Probar end-to-end** con el informe real de Intel que está en local.
4. **Mejorar la pantalla de análisis** para mostrar los datos extraídos (métricas, señal).

---

## Estado actual — infraestructura completamente implementada

### Backend — todo funciona, solo falta activar Gemini en config

**Servicios Docker** (`docker-compose.yml`): `backend`, `db`, `redis`, `frontend`, `worker`.
El servicio `worker` ya corre Celery con el comando:
```
celery -A app.worker:celery_app worker --loglevel=info
```
Todos los servicios leen el fichero `.env` (opcional, `required: false`).

**ORM** (`backend/app/db/models/ai_report.py`):
- `UploadedFile` — PDF en columna BYTEA, FK a `holdings` + `users` con CASCADE.
- `AnalysisJob` — ciclo de vida del task: `queued → running → succeeded/failed`.
  Campos clave: `status`, `attempt_count`, `last_error`, `analysis_report_id` (UUID plano,
  no FK para evitar FK circular), `started_at`, `completed_at`.
- `AnalysisReport` — resultado inmutable: `report_date`, `provider`, `model_version`,
  `extracted_metrics` (JSONB), `executive_summary`, `global_signal` (bullish/neutral/bearish),
  `confidence_notes`, `raw_response` (JSONB).

**Celery task** (`backend/app/worker/tasks.py` — `analyze_report_task`):
- Máximo 3 intentos. Backoff: 60 s → 300 s → 900 s.
- `NonRetryableError` para errores de config/auth (no reintentar).
- Flujo: carga job → PDF bytes → asset context → llama `provider.extract_from_pdf()` →
  valida resultado → persiste `AnalysisReport` → llama `_write_indicator_snapshots()` →
  marca `succeeded`.
- `_write_indicator_snapshots()` upserta `IndicatorSnapshot` para indicadores con
  `update_strategy='on_ai_analysis'`: `per`, `roe`, `debt_ebitda`, `revenue_growth_yoy`,
  `analyst_sentiment`. Estos son los indicadores fundamentales que aparecen en las tarjetas
  del asset-detail-screen una vez procesado el informe.

**AI Providers** (`backend/app/services/ai_providers/`):
- `base.py` — `AIProvider` ABC + `AIExtractionResult`. El `_parse_response()` limpia
  markdown fences, parsea JSON y valida con Pydantic (`ExtractionOutput`).
- `gemini_provider.py` — usa `google-genai>=1.5.0` (SDK nuevo, **NO** `google-generativeai`).
  Envía PDF nativamente: `types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")`.
  Cliente: `genai.Client(api_key=...)`. Async via `asyncio.to_thread`.
- `factory.py` — lee API key de env vars: `AI_GEMINI_API_KEY`.
- `anthropic_provider.py`, `openai_provider.py` — también implementados (no prioritarios).

**Endpoints** (`backend/app/api/ai_reports.py`):
```
POST   /portfolios/{pid}/holdings/{hid}/ai-reports      → upload PDF, devuelve 202 + job_id
GET    /portfolios/{pid}/holdings/{hid}/ai-reports      → lista AnalysisReportSummary[]
GET    /ai-reports/jobs                                 → lista jobs del usuario (con ?status_filter=)
GET    /ai-reports/{report_id}                          → AnalysisReportDetail (con extracted_metrics)
DELETE /ai-reports/{report_id}                          → elimina report + cascade
```

**Schemas de respuesta** (`backend/app/api/d07_schemas.py`):
```python
class AnalysisReportSummary:      # devuelto por GET /ai-reports (lista)
    id, holding_id, report_date, provider, model_version,
    global_signal, executive_summary, created_at

class AnalysisReportDetail:       # devuelto por GET /ai-reports/{id}
    id, holding_id, uploaded_file_id, analysis_job_id,
    report_date, provider, model_version,
    extracted_metrics,  # dict con per, roe, debt_ebitda, revenue_growth_yoy, analyst_sentiment
    executive_summary, global_signal, confidence_notes, created_at
```

**Prompt + schema**:
- `backend/ai_extraction_prompt.md` — instrucciones al LLM con placeholders `{ticker}`,
  `{name}`, `{asset_type}`, `{quote_currency}`. Extrae: `per`, `roe`, `debt_ebitda`,
  `revenue_growth_yoy`, `analyst_sentiment`, `report_date`, `executive_summary` (3-5 bullets),
  `global_signal`, `confidence_notes`. Exige JSON puro en la respuesta.
- `backend/ai_extraction_schema.json` — JSON Schema para validación Pydantic del output.

**Dependencias** (`backend/requirements.txt`):
- `google-genai==1.5.0` ✅ ya está
- `celery[redis]==5.4.0` ✅ ya está
- `python-multipart==0.0.20` ✅ ya está (necesario para `UploadFile`)

### Frontend — componentes listos, pero API client tiene bugs (ver abajo)

**Pantalla de análisis** (`frontend/src/screens/analysis-screen.ts`,
ruta `/portfolios/:pid/assets/:hid/analysis`):
- Renderiza `<pi-pdf-uploader>` (drag & drop o click para subir PDF).
- Lista reports del holding: estado, nombre de archivo, fecha, `executive_summary`.
- Escucha evento `upload-complete` del uploader y recarga la lista.
- **Pendiente mejorar**: no muestra `global_signal`, `extracted_metrics` ni `confidence_notes`.

**Componente uploader** (`frontend/src/components/pdf-uploader.ts`):
- Custom element `<pi-pdf-uploader>`. Propiedad `holdingId: string`.
- Emite `CustomEvent('upload-complete')` cuando el POST termina.
- El análisis-screen adjunta `afterRender()` el listener sobre el elemento.

**API client análisis** (`frontend/src/api/analyses.ts`) — ⚠️ TIENE BUGS (ver sección siguiente):
```typescript
uploadPdf(holdingId, file)  // ← URL incorrecta + falta portfolioId + falta CSRF
listReports(holdingId)      // ← URL incorrecta + falta portfolioId
getNotifications()          // ← URL incorrecta
```

**Tipo en frontend** (`frontend/src/api/types.ts`) — ⚠️ NO COINCIDE con el backend:
```typescript
// Tipo actual (incorrecto / incompleto):
export interface AiReport {
  id: string;
  holding_id: string;
  status: AnalysisStatus;        // ← no existe en AnalysisReportSummary del backend
  pdf_filename: string | null;   // ← no existe en AnalysisReportSummary del backend
  summary: string | null;        // ← backend lo llama executive_summary
  created_at: string;
  completed_at: string | null;   // ← no existe en AnalysisReportSummary
  error_message: string | null;  // ← no existe en AnalysisReportSummary
}
```

---

## Paso 1 — Activar Gemini (cambios de configuración)

### `backend/config.yaml` — cambiar proveedor y modelo

```yaml
ai:
  provider: gemini          # ← cambiar de "anthropic" a "gemini"
  gemini:
    model: gemini-2.0-flash # ← cambiar de "gemini-2.5-pro" (de pago) a "gemini-2.0-flash" (gratis)
  per_call_timeout_seconds: 120
```

### `.env` — la API key YA está configurada

La variable `AI_GEMINI_API_KEY` ya está en el fichero `.env` del backend.
**Si al ejecutar el worker aparece el error `AI_GEMINI_API_KEY is not set`, verificar:**
1. Que el servicio `worker` en docker-compose tiene `env_file: - path: .env` (ya lo tiene).
2. Que el fichero `.env` está en la raíz del proyecto (al lado de `docker-compose.yml`),
   no dentro de `backend/`.
3. Reiniciar con `docker compose up -d --force-recreate worker` para que tome los nuevos valores.

Tras cambiar `config.yaml`, reiniciar solo el backend y el worker:
```powershell
docker compose restart backend worker
```

---

## Paso 2 — Bugs conocidos a corregir en el frontend

### Bug 1: URLs incorrectas en `frontend/src/api/analyses.ts`

Las URLs actuales no coinciden con los endpoints del backend. Hay que reescribir el cliente:

| Función actual | URL actual (incorrecta) | URL correcta del backend |
|---|---|---|
| `uploadPdf(holdingId, file)` | `/holdings/{hid}/analyses` | `POST /portfolios/{pid}/holdings/{hid}/ai-reports` |
| `listReports(holdingId)` | `/holdings/{hid}/analyses` | `GET /portfolios/{pid}/holdings/{hid}/ai-reports` |
| `getNotifications()` | `/me/notifications` | `GET /ai-reports/jobs?status_filter=queued,running` |

Además, `uploadPdf` usa `fetch` directamente sin el header `X-CSRF-Token`, y sin pasar
`portfolioId`. Hay que:
- Añadir `portfolioId` como parámetro a `uploadPdf` y `listReports`.
- Usar el helper `post()` del cliente o añadir el CSRF token manualmente.
- Corregir las URLs para que coincidan con el backend.

### Bug 2: Tipo `AiReport` no coincide con `AnalysisReportSummary` del backend

Hay que reemplazar la interfaz `AiReport` en `frontend/src/api/types.ts` con dos tipos que
reflejen exactamente los schemas del backend (`d07_schemas.py`):

```typescript
// Nuevo tipo para la lista (GET /portfolios/{pid}/holdings/{hid}/ai-reports)
export interface AiReportSummary {
  id: string;
  holding_id: string;
  report_date: string | null;        // "YYYY-MM-DD"
  provider: string;
  model_version: string;
  global_signal: 'bullish' | 'neutral' | 'bearish' | null;
  executive_summary: string;
  created_at: string;
}

// Nuevo tipo para el detalle (GET /ai-reports/{report_id})
export interface AiReportDetail extends AiReportSummary {
  uploaded_file_id: string | null;
  analysis_job_id: string;
  extracted_metrics: {
    per: number | null;
    roe: number | null;
    debt_ebitda: number | null;
    revenue_growth_yoy: number | null;
    analyst_sentiment: 'bullish' | 'mixed' | 'bearish' | null;
  };
  confidence_notes: string | null;
}
```

El tipo `Notification` sigue siendo correcto (usado en `header-bar.ts`).

### Bug 3: `analysis-screen.ts` necesita recibir `portfolioId`

La pantalla recibe `params` con `portfolioId` y `holdingId`, pero actualmente solo usa
`holdingId` al llamar `listReports`. Tras corregir el cliente, habrá que pasar ambos.

---

## Paso 3 — Mejorar la pantalla de análisis

Tras corregir los bugs, mejorar `frontend/src/screens/analysis-screen.ts` para mostrar:

- **`global_signal`** con badge de color: verde = bullish, amarillo = neutral, rojo = bearish.
- **`report_date`** si está disponible.
- **Métricas extraídas** (PER, ROE, Deuda/EBITDA, Crecimiento YoY, Sentimiento analista)
  en una tabla o grid compacto. Para cada métrica mostrar el valor y una interpretación
  funcional breve (usando las descripciones que ya existen en `es.json`/`en.json` bajo
  `indicator.per.tooltip`, `indicator.roe.tooltip`, etc.).
- **`confidence_notes`** si no es null.
- **Botón eliminar** inline con confirmación (patrón `_confirmDeleteId: string | null`
  igual que en otras pantallas).

Añadir los i18n keys que falten en `es.json` y `en.json`:
```json
"analysis.global_signal": "Señal global",
"analysis.global_signal.bullish": "Alcista",
"analysis.global_signal.neutral": "Neutral",
"analysis.global_signal.bearish": "Bajista",
"analysis.report_date": "Fecha del informe",
"analysis.metrics": "Métricas extraídas",
"analysis.confidence_notes": "Notas de confianza",
"analysis.delete": "Eliminar informe",
"analysis.delete.confirm": "¿Eliminar este informe? Se eliminarán también los indicadores generados.",
"analysis.uploading": "Subiendo...",
"analysis.drop_pdf": "Arrastra un PDF aquí o haz clic para seleccionar",
"analysis.or_click": "Formatos soportados: PDF · Máx. 20 MB",
"analysis.upload_success": "Informe subido. Analizando en segundo plano..."
```

---

## Paso 4 — Test end-to-end con el informe de Intel

El informe está en local:
```
C:\Users\RomerCepeda\Downloads\intel Q4 2026 0000050863-26-000079.pdf
```

**Intel** debe estar ya añadido como activo en alguna cartera (ticker: `INTC`).
El flujo completo a verificar:
1. Ir a `/portfolios/:pid/assets/:hid/analysis` del activo Intel.
2. Subir el PDF desde la zona de drop (o click para seleccionar el archivo de la ruta anterior).
3. El backend devuelve 202. El job aparece en estado `queued`.
4. El worker Celery lo procesa → llama a Gemini 2.0 Flash con el PDF → recibe JSON extraído.
5. Job pasa a `succeeded`. El report aparece en la lista con `executive_summary`.
6. Los `IndicatorSnapshot` se upserten en DB: PER, ROE, etc. aparecen en las tarjetas
   de indicadores del asset-detail-screen.

**Logs útiles durante el test:**
```powershell
# Ver logs del worker Celery (donde se ejecuta el análisis IA)
docker compose logs -f worker

# Ver logs del backend (para errores de validación o API)
docker compose logs -f backend
```

**Puntos de fallo habituales:**
- **`AI_GEMINI_API_KEY is not set`**: el `.env` no se está leyendo. Verificar ubicación y
  reiniciar con `docker compose up -d --force-recreate worker`.
- **`parse_status='invalid_json'`**: Gemini no devolvió JSON puro. Puede pasar con
  `gemini-2.0-flash` si no sigue las instrucciones del prompt. Solución: añadir en el
  prompt una línea explícita "IMPORTANT: Return ONLY the JSON object, nothing else, no
  markdown fences, no preamble" y/o probar con `gemini-1.5-flash`.
- **Timeout**: el PDF de Intel puede ser grande. Aumentar en `config.yaml`:
  `per_call_timeout_seconds: 180`.
- **Job queda en `queued` forever**: el worker no está corriendo o Redis no está disponible.
  Verificar con `docker compose ps` que los servicios `worker` y `redis` están `running`.

---

## Archivos clave a leer antes de empezar

```
backend/config.yaml                                    ← cambiar provider: gemini + model
backend/app/api/ai_reports.py                          ← endpoints exactos (URLs correctas)
backend/app/api/d07_schemas.py                         ← schemas de respuesta (referencia para tipos TS)
backend/app/worker/tasks.py                            ← Celery task completo
backend/app/services/ai_providers/gemini_provider.py  ← implementación Gemini
backend/ai_extraction_prompt.md                        ← prompt enviado al LLM
frontend/src/api/analyses.ts                           ← corregir URLs y firma de funciones
frontend/src/api/types.ts                              ← corregir/ampliar AiReport
frontend/src/screens/analysis-screen.ts               ← mejorar UI
frontend/src/i18n/locales/es.json                     ← añadir keys de análisis
frontend/src/i18n/locales/en.json                     ← añadir keys de análisis
```

---

## Convenciones de pantalla (recordatorio)

- Cada screen es Custom Element que extiende `BaseComponent`.
- `render()` → string HTML con `<style>` inline usando `var(--...)`.
- `afterRender()` → event listeners. Nunca `onclick` inline.
- Cuando `shadow.innerHTML = this.render()` se hace manualmente, llamar `this.afterRender()`.
- Confirmaciones inline con `_confirmXxx: string | null`. Sin `window.confirm()` ni `alert()`.
- Errores inline con `color: var(--color-danger)`. Sin `alert()`.
- `t(key)` para todos los textos de UI.
- Después de cada cambio de modelo, `.\scripts\db.ps1 generate "msg"` + `upgrade`.
