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
from app.api.ai_reports import router as ai_reports_router
from app.api.assets import router as assets_router
from app.api.auth import router as auth_router
from app.api.fx_calc import router as fx_calc_router
from app.api.health import router as health_router
from app.api.holdings import router as holdings_router
from app.api.indicators import router as indicators_router
from app.api.market_data import router as market_data_router
from app.api.portfolios import router as portfolios_router
from app.api.price_levels import router as price_levels_router
from app.config import get_config
from app.db.session import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load and validate config.yaml at import time.
# The application refuses to start if the file is missing or invalid (Spec 00f §4).
_config = get_config()
logger.info("Configuration loaded — AI provider: %s", _config.ai.provider)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: seed the indicator and roles/permissions catalogs. Shutdown: nothing to clean up."""
    from app.roles.seed_loader import seed_roles_catalog
    from app.services.indicator_service import seed_indicators

    async with AsyncSessionLocal() as db:
        await seed_indicators(db)
        await seed_roles_catalog(db)

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
app.include_router(market_data_router)
app.include_router(indicators_router)
app.include_router(ai_reports_router)
