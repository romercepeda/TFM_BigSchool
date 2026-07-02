"""D06 — Price Levels, Alert Engine & Analysis History API endpoints (Spec D06).

All routes are nested under /portfolios/{portfolio_id}/holdings/{holding_id}/.

Endpoints:
    GET    .../price-levels                  — list active levels for a holding
    POST   .../price-levels                  — batch-create one or more levels
    PATCH  .../price-levels/{lid}            — edit a level (rules from §3.2)
    DELETE .../price-levels/{lid}            — hard-delete (writes 'removed' history first)
    GET    .../price-levels/history          — full immutable history for a holding
    POST   .../price-levels/evaluate         — manual alert crossing trigger (pre-D09 testing)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.d06_schemas import (
    EvaluateRequest,
    EvaluateResponse,
    PriceLevelBatchIn,
    PriceLevelDeleteRequest,
    PriceLevelHistoryEntryResponse,
    PriceLevelPatch,
    PriceLevelResponse,
)
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services import price_level_service as svc
from app.services.lot_service import get_holding_with_asset
from app.services.portfolio_service import get_portfolio_by_id

router = APIRouter(
    prefix="/portfolios/{portfolio_id}/holdings/{holding_id}/price-levels",
    tags=["price-levels"],
)

_NOT_FOUND_PORTFOLIO = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found."
)
_NOT_FOUND_HOLDING = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found."
)
_NOT_FOUND_LEVEL = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Price level not found."
)


def _bad_request(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


async def _require_holding(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User,
    db: AsyncSession,
):
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND_PORTFOLIO
    holding = await get_holding_with_asset(db, holding_id, portfolio_id)
    if holding is None:
        raise _NOT_FOUND_HOLDING
    return holding


# ── List active levels ────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[PriceLevelResponse],
    dependencies=[Depends(require_permission("price_level.view"))],
)
async def list_price_levels(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PriceLevelResponse]:
    """Return all active price levels for a holding, ordered by creation date."""
    await _require_holding(portfolio_id, holding_id, current_user, db)
    levels = await svc.list_price_levels(db, holding_id)
    return [PriceLevelResponse.model_validate(lv) for lv in levels]


# ── Batch create ──────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=list[PriceLevelResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("price_level.create"))],
)
async def create_price_levels(
    portfolio_id: UUID,
    holding_id: UUID,
    body: PriceLevelBatchIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PriceLevelResponse]:
    """Create one or more price levels in a single atomic submission (Spec D06 §8).

    Each level gets its own 'created' history entry in the same transaction.
    """
    await _require_holding(portfolio_id, holding_id, current_user, db)

    level_dicts = [
        {"direction": lv.direction, "target_price": lv.target_price, "note": lv.note}
        for lv in body.levels
    ]

    try:
        created = await svc.create_price_levels(
            db,
            holding_id,
            level_dicts,
            asset_price_at_event=body.asset_price_at_event,
        )
    except ValueError as exc:
        raise _bad_request(str(exc))

    await db.commit()
    for lv in created:
        await db.refresh(lv)

    return [PriceLevelResponse.model_validate(lv) for lv in created]


# ── Edit ──────────────────────────────────────────────────────────────────────


@router.patch(
    "/{level_id}",
    response_model=PriceLevelResponse,
    dependencies=[Depends(require_permission("price_level.edit"))],
)
async def edit_price_level(
    portfolio_id: UUID,
    holding_id: UUID,
    level_id: UUID,
    body: PriceLevelPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PriceLevelResponse:
    """Edit a price level. Touched levels can only change their note (Spec D06 §3.2)."""
    await _require_holding(portfolio_id, holding_id, current_user, db)

    level = await svc.get_price_level(db, level_id, holding_id)
    if level is None:
        raise _NOT_FOUND_LEVEL

    try:
        level = await svc.edit_price_level(
            db,
            level,
            direction=body.direction,
            target_price=body.target_price,
            note=body.note,
            asset_price_at_event=body.asset_price_at_event,
        )
    except ValueError as exc:
        raise _conflict(str(exc))

    await db.commit()
    await db.refresh(level)
    return PriceLevelResponse.model_validate(level)


# ── Delete ────────────────────────────────────────────────────────────────────


@router.delete(
    "/{level_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("price_level.delete"))],
)
async def delete_price_level(
    portfolio_id: UUID,
    holding_id: UUID,
    level_id: UUID,
    body: PriceLevelDeleteRequest = PriceLevelDeleteRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard-delete a price level. A 'removed' history entry is written first (Spec D06 §3.3)."""
    await _require_holding(portfolio_id, holding_id, current_user, db)

    level = await svc.get_price_level(db, level_id, holding_id)
    if level is None:
        raise _NOT_FOUND_LEVEL

    await svc.delete_price_level(
        db, level, asset_price_at_event=body.asset_price_at_event
    )
    await db.commit()


# ── History (immutable, append-only) ─────────────────────────────────────────


@router.get(
    "/history",
    response_model=list[PriceLevelHistoryEntryResponse],
    dependencies=[Depends(require_permission("price_level.view"))],
)
async def list_price_level_history(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PriceLevelHistoryEntryResponse]:
    """Return the full immutable analysis history for a holding (Spec D06 §7).

    Ordered by event_at descending (most recent first).
    """
    await _require_holding(portfolio_id, holding_id, current_user, db)
    entries = await svc.list_price_level_history(db, holding_id)
    return [PriceLevelHistoryEntryResponse.model_validate(e) for e in entries]


# ── Manual alert evaluation (pre-D09 testing hook) ───────────────────────────


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    dependencies=[Depends(require_permission("price_level.edit"))],
)
async def evaluate_crossings(
    portfolio_id: UUID,
    holding_id: UUID,
    body: EvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvaluateResponse:
    """Manually run the alert crossing logic for a holding (Spec D06 §5.2).

    In production this is triggered by the D09 daily price-update job.
    This endpoint allows testing the alert engine before D09 is available.
    Levels that cross are permanently marked as 'touched'.
    """
    await _require_holding(portfolio_id, holding_id, current_user, db)

    armed_before = await svc.list_price_levels(db, holding_id)
    armed_count = sum(1 for lv in armed_before if lv.status == "armed")

    touched = await svc.apply_crossings(
        db,
        holding_id,
        previous_close=body.previous_close,
        current_close=body.current_close,
        close_date=body.close_date,
    )

    await db.commit()
    for lv in touched:
        await db.refresh(lv)

    return EvaluateResponse(
        holding_id=holding_id,
        levels_touched=[PriceLevelResponse.model_validate(lv) for lv in touched],
        levels_evaluated=armed_count,
    )
