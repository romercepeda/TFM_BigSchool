"""Assets API endpoint — Spec D03 §3.1."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d03_schemas import AssetPatch, AssetResponse
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services.asset_service import search_assets, update_asset

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get(
    "/search",
    response_model=list[AssetResponse],
    dependencies=[Depends(require_permission("holding.add_asset"))],
)
async def search(
    q: str = Query(min_length=1, description="Ticker prefix or name substring."),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssetResponse]:
    """Search for assets by ticker prefix or name substring (typeahead support)."""
    assets = await search_assets(db, q, limit=limit)
    return [AssetResponse.model_validate(a) for a in assets]


@router.patch(
    "/{asset_id}",
    response_model=AssetResponse,
    dependencies=[Depends(require_permission("holding.add_asset"))],
)
async def patch_asset(
    asset_id: UUID,
    body: AssetPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    """Update ticker, name and/or market of an asset."""
    asset = await update_asset(db, asset_id, ticker=body.ticker, name=body.name, market=body.market)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    await db.commit()
    return AssetResponse.model_validate(asset)
