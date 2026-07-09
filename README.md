# Portfolio IA — BigSchool

Aplicación web (mobile-first) para la gestión personal de carteras de inversión (acciones, ETFs, fondos y Bitcoin), con seguimiento de indicadores técnicos y fundamentales, definición de niveles de precio objetivo con alertas, y análisis de informes financieros mediante IA.

Trabajo Fin de Máster (TFM) — desarrollado siguiendo una metodología de **Spec Driven Development**: cada funcionalidad implementada corresponde a una especificación aprobada y versionada en [`specs/`](specs/).

> Demo desplegada en Azure: https://portfolio-ia-frontend.icysand-40c562ef.northeurope.azurecontainerapps.io

---

## a. Descripción general

Portfolio IA permite a una persona con pocos conocimientos técnicos:

- Gestionar **varias carteras**, cada una con su propia moneda base.
- Registrar activos (acciones, ETFs, fondos, Bitcoin) y sus **lotes de compra**, con conversión de divisa automática y corrección manual.
- Consultar **indicadores técnicos** (MA200, cruce MA50/200, RSI14, MACD...) y **fundamentales** (PER, ROE, deuda/EBITDA, crecimiento de ingresos...) con su histórico, definidos en un catálogo configurable (no en código).
- Definir **niveles de precio objetivo** de compra/venta, con un motor de alertas que detecta cuándo el precio los cruza.
- Subir **informes financieros en PDF** y obtener un análisis automático (resumen, señal, métricas) generado por IA (Anthropic Claude, OpenAI o Gemini, configurable).
- Ver KPIs de cartera calculados en la moneda base: rentabilidad total (TWR), rentabilidad anualizada (CAGR), drawdown máximo, volatilidad y ratio de Sharpe.
- Todo bajo un sistema de **roles y permisos** (Administrador / Inversor) e **internacionalización** completa (español/inglés).

El diseño está pensado como MVP de usuario único, pero con arquitectura preparada desde el inicio para multi-usuario (de hecho, ya soporta múltiples cuentas con aislamiento de datos por usuario).

---

## b. Stack tecnológico

### Backend
| Componente | Tecnología |
|---|---|
| Lenguaje / framework | Python 3.12 + FastAPI |
| ORM / migraciones | SQLAlchemy 2.0 (async) + Alembic |
| Validación | Pydantic v2 |
| Base de datos | PostgreSQL 16 |
| Tareas asíncronas | Celery + Redis (análisis de PDFs con IA) |
| Autenticación | JWT (cookie httpOnly) + OAuth Google/Microsoft + email+contraseña + invitado |
| Autorización | RBAC propio (roles y permisos data-driven, `roles_catalog.yaml`) |
| Proveedores de IA | Anthropic Claude (por defecto) / OpenAI / Gemini — cascada configurable |
| Datos de mercado | Twelve Data / EODHD / Finnhub — cascada de proveedores con fallback automático |
| Tipos de cambio | Frankfurter (datos BCE, gratuito, sin API key) |
| Linter / formateo | Ruff |
| Tests | pytest + pytest-cov |

### Frontend
| Componente | Tecnología |
|---|---|
| UI | **Web Components nativos** (`customElements.define`, sin framework) |
| Reactividad | `@preact/signals-core` (~2KB) |
| Build | Vite + TypeScript |
| Estilos | CSS plano con custom properties (temas: pastel, oscuro, océano, bosque, terminal) |
| Tests | Vitest + `@open-wc/testing` |
| i18n | Sistema propio, catálogo de traducciones en `frontend/src/i18n/locales/` (es/en) |

### Infraestructura
- Docker + Docker Compose para desarrollo local (backend, worker, db, redis, frontend).
- Despliegue en **Azure Container Apps** (backend, worker, frontend) + **Azure Database for PostgreSQL Flexible Server** + Redis (Upstash, free tier).

---

## c. Instalación y ejecución

### Requisitos previos
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) en ejecución.
- [Node.js](https://nodejs.org/) 20+ (para el frontend en modo desarrollo).
- (Opcional) claves de API para proveedores de datos de mercado e IA — la app funciona sin ellas, pero esas funcionalidades concretas quedarán deshabilitadas.

### 1. Clonar y configurar variables de entorno

```powershell
git clone https://github.com/romercepeda/TFM_BigSchool.git
cd TFM_BigSchool
copy .env.example .env
```

Edita `.env` y completa las claves que quieras usar (OAuth, proveedores de datos de mercado, proveedores de IA). El backend arranca sin ellas; solo fallan las funcionalidades que dependan de la clave ausente.

### 2. Arrancar el backend (Docker)

```powershell
docker compose up backend db redis
```

Espera a ver `Application startup complete.` La primera vez, el sistema:
- Aplica las migraciones pendientes.
- Siembra el catálogo de indicadores y de roles/permisos.
- Crea la cuenta de administrador inicial si no existe ninguna (contraseña aleatoria mostrada una única vez en el log).

> El servicio `worker` (Celery) solo es necesario para el análisis de informes PDF con IA: `docker compose up worker`.

### 3. Arrancar el frontend (modo desarrollo)

En otra terminal:

```powershell
cd frontend
npm install
npm run dev
```

Espera a ver `Local: http://localhost:5173/` y abre esa URL en el navegador.

> **Importante:** `docker-compose.yml` también define un servicio `frontend` (build estática con nginx) que ocupa el puerto 5173. Si está corriendo, para en desarrollo con `docker compose stop frontend` para evitar conflictos de puerto y CORS.

### 4. Migraciones y base de datos

Todas las operaciones de base de datos se gestionan con `scripts/db.ps1` (ejecuta dentro del contenedor del backend, no requiere Python local):

```powershell
.\scripts\db.ps1 upgrade              # aplicar migraciones pendientes
.\scripts\db.ps1 generate "mensaje"   # generar migración tras cambiar un modelo
.\scripts\db.ps1 history              # ver historial de migraciones
.\scripts\db.ps1 current              # ver revisión actual
.\scripts\db.ps1 reset                # ⚠️ borra todos los datos y reaplica migraciones
```

### 5. Tests

```powershell
# Backend
docker compose exec backend pytest

# Frontend
cd frontend
npm test
```

---

## d. Estructura del proyecto

```
TFM_BigSchool/
├── backend/                     # API FastAPI
│   ├── app/
│   │   ├── api/                 # Endpoints REST (auth, portfolios, holdings, indicators, admin...)
│   │   ├── auth/                # JWT, hashing de contraseñas, CSRF, dependencias de sesión
│   │   ├── roles/                # RBAC: catálogo de roles/permisos, seed, bootstrap del admin
│   │   ├── db/
│   │   │   └── models/          # Modelos ORM (User, Portfolio, Asset, Lot, PriceLevel...)
│   │   ├── services/             # Lógica de negocio (FX engine, market data, indicadores, IA...)
│   │   │   ├── ai_providers/    # Adaptadores Anthropic / OpenAI / Gemini
│   │   │   └── market_data/     # Adaptadores Twelve Data / EODHD / Finnhub (cascada)
│   │   ├── worker/               # Tareas Celery (análisis de PDF)
│   │   └── config.py             # Carga tipada de config.yaml (fail-fast)
│   ├── migrations/                # Migraciones Alembic
│   ├── config.yaml                # Configuración de comportamiento (no secretos)
│   ├── roles_catalog.yaml         # Catálogo de roles y permisos (fuente de verdad RBAC)
│   ├── indicators_catalog.yaml    # Catálogo de indicadores técnicos/fundamentales
│   └── tests/
├── frontend/                     # Web Components + Vite
│   └── src/
│       ├── screens/               # Pantallas (pi-dashboard-screen, pi-login-screen...)
│       ├── components/            # Componentes reutilizables
│       ├── api/                   # Clientes HTTP hacia el backend
│       ├── state/                 # Signals globales (auth, portfolio, tema, idioma...)
│       ├── router/                # Enrutador propio (~50 líneas)
│       └── i18n/                  # Traducciones es/en
├── specs/                        # Especificaciones funcionales versionadas (Spec Driven Development)
│   ├── 00-engineering/            # Specs transversales (convenciones, seguridad, testing, Docker...)
│   ├── domain/                    # Specs de dominio D01–D12 (auth, carteras, activos, IA, roles...)
│   └── changesets/                # Changesets incrementales sobre las specs base
├── scripts/                      # Scripts de gestión (db.ps1, switch-to-client...)
├── docker-compose.yml
└── .env.example
```

---

## e. Funcionalidades principales

- **Autenticación multi-proveedor**: registro/login con email+contraseña, Google, Microsoft o modo invitado.
- **Gestión de carteras**: crear, renombrar, archivar, restaurar y eliminar carteras; cada una con su propia moneda base.
- **Activos y lotes de compra**: alta de activos (acciones, ETFs, fondos, Bitcoin), registro de lotes con FIFO para ventas, tipo de cambio automático o manual por lote.
- **Motor de cálculo de divisas**: separa el rendimiento del activo del efecto del tipo de cambio, agregado a nivel de cartera.
- **Catálogo de indicadores**: técnicos (MA200, cruce MA50/200, RSI14, MACD) y fundamentales (PER, ROE, deuda/EBITDA...), con histórico y zonas de evaluación (positivo/neutro/atención) configurables sin tocar código.
- **Niveles de precio y alertas**: definición de precio objetivo de compra/venta con histórico inmutable y motor de detección de cruces.
- **Análisis de informes con IA**: subida de PDF, extracción de señales y métricas mediante Anthropic/OpenAI/Gemini (cascada configurable), reintentos automáticos vía Celery.
- **Datos de mercado resilientes**: cascada de proveedores (Twelve Data → EODHD → Finnhub) con failover automático y reporte de fallos.
- **Roles y permisos (RBAC)**: catálogo data-driven con dos roles v1 (Administrador / Inversor), ~35 permisos granulares, panel de administración (gestión de usuarios y roles) y garantía de "siempre al menos un administrador".
- **Internacionalización**: interfaz completa en español e inglés, incluidos los textos del catálogo de indicadores.
- **Landing page comercial** con branding propio, independiente de la aplicación autenticada.
- **Temas visuales**: pastel, oscuro, océano, bosque y terminal.
