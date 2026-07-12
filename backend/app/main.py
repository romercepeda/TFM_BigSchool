"""BigSchool API — application entry point.

Starts the FastAPI application, loads and validates config.yaml (fail-fast),
seeds the indicator and roles/permissions catalogs, and registers all API routers.

Run via Docker Compose:
    docker compose up backend

Run locally (requires local Python env with requirements.txt installed):
    uvicorn app.main:app --reload
"""

# Load .env from project root for local dev — no-op in Docker (env vars already injected).
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / '.env', override=False)

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.csrf import csrf_middleware
from app.api.admin import router as admin_router
from app.api.ai_reports import router as ai_reports_router
from app.api.assets import router as assets_router
from app.api.auth import router as auth_router
from app.api.date_alerts import router as date_alerts_router
from app.api.fx_calc import router as fx_calc_router
from app.api.health import router as health_router
from app.api.holdings import router as holdings_router
from app.api.indicators import router as indicators_router
from app.api.market_data import router as market_data_router
from app.api.me import router as me_router
from app.api.portfolios import router as portfolios_router
from app.api.price_levels import router as price_levels_router
from app.api.settings import router as settings_router
from app.config import get_config, validate_provider_api_keys
from app.db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load and validate config.yaml at import time.
# The application refuses to start if the file is missing or invalid (Spec 00f §4).
_config = get_config()
logger.info("Configuration loaded — AI provider: %s", _config.ai.provider)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: load settings overlay, validate provider keys, seed catalogs,
    backfill roles, validate coverage, bootstrap admin.

    Shutdown: nothing to clean up.
    """
    from app.roles.bootstrap import ensure_admin_exists, verify_always_one_admin
    from app.roles.seed_loader import seed_roles_catalog
    from app.roles.service import backfill_default_roles
    from app.roles.validation import validate_permission_coverage
    from app.services import settings_overlay
    from app.services.indicator_service import seed_indicators

    async with AsyncSessionLocal() as db:
        # Load the system_settings DB overlay (Changeset C04 §5) before the
        # API key check below, so it validates the *effective* provider list
        # (config.yaml overridden by any saved admin edit), not just the file.
        await settings_overlay.load_overrides(db)
        effective_market_data_providers = settings_overlay.get_market_data_providers(
            _config.market_data.providers
        )
        # Fail fast if a cascade provider has no API key (Spec D12 §10).
        validate_provider_api_keys(_config, effective_market_data_providers)

        await seed_indicators(db)
        await seed_roles_catalog(db)
        # Existing users predate D11 — give them the default role once (C02 §3).
        await backfill_default_roles(db)
        # Fail fast if any route is missing (or has a stale) require_permission (D11 §8.3).
        await validate_permission_coverage(app, db)
        # Create the configured admin on a fresh DB (D11 §6.1), then independently
        # verify the always-one-admin invariant still holds (D11 §6.3).
        await ensure_admin_exists(db)
        await verify_always_one_admin(db)

    yield


app = FastAPI(
    title="BigSchool API",
    version="0.1.0",
    description="Financial portfolio management API — TFM BigSchool",
    lifespan=lifespan,
)

# CORS — must be added before CSRF so OPTIONS preflights are answered first.
# allow_credentials=True requires explicit origins (no wildcard).
_frontend_origin = os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(csrf_middleware)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(portfolios_router)
app.include_router(holdings_router)
app.include_router(assets_router)
app.include_router(fx_calc_router)
app.include_router(price_levels_router)
app.include_router(date_alerts_router)
app.include_router(market_data_router)
app.include_router(indicators_router)
app.include_router(ai_reports_router)
app.include_router(me_router)
app.include_router(admin_router)
app.include_router(settings_router)
