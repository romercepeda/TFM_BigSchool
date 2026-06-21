"""Health check endpoint.

GET /health — used by Docker, load balancers, and developers to verify the API is up.
Returns 200 with a minimal JSON body. No authentication required.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return service health status."""
    return HealthResponse(status="ok", version="0.1.0")
