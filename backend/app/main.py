"""BigSchool API — application entry point.

Starts the FastAPI application, loads and validates config.yaml (fail-fast),
and registers all API routers.

Run via Docker Compose:
    docker compose up backend

Run locally (requires local Python env with requirements.txt installed):
    uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI

from app.api.assets import router as assets_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.holdings import router as holdings_router
from app.api.portfolios import router as portfolios_router
from app.config import get_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load and validate config.yaml at import time.
# The application refuses to start if the file is missing or invalid (Spec 00f §4).
_config = get_config()
logger.info("Configuration loaded — AI provider: %s", _config.ai.provider)

app = FastAPI(
    title="BigSchool API",
    version="0.1.0",
    description="Financial portfolio management API — TFM BigSchool",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(portfolios_router)
app.include_router(holdings_router)
app.include_router(assets_router)
