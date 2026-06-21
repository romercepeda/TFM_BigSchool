"""Assets API endpoint — Spec D03 §3.1.

Endpoint:
    GET /assets/search?q= — search existing assets by ticker prefix or name.

Assets are shared reference data and are created implicitly via POST /holdings.
There is no standalone POST /assets endpoint: creation is always tied to
the "add asset to portfolio" flow (Spec D03 §4).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d03_schemas import AssetResponse
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.asset_service import search_assets

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/search", response_model=list[AssetResponse])
async def search(
    q: str = Query(min_length=1, description="Ticker prefix or name substring."),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssetResponse]:
    """Search for assets by ticker prefix or name substring (typeahead support)."""
    assets = await search_assets(db, q, limit=limit)
    return [AssetResponse.model_validate(a) for a in assets]
