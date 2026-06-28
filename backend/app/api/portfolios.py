"""Portfolio API endpoints — Spec D02.

Endpoints:
    POST   /portfolios                    — create a new portfolio
    GET    /portfolios                    — list portfolios (active by default)
    PATCH  /portfolios/{id}               — rename a portfolio
    POST   /portfolios/{id}/archive       — archive (soft-delete)
    POST   /portfolios/{id}/restore       — restore from archive
    DELETE /portfolios/{id}               — permanent delete (only if archived)

All endpoints require a valid Bearer JWT (get_current_user dependency).
A user can only access portfolios where user_id matches their own identity (Spec D02 §11).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.portfolio_schemas import (
    CreatePortfolioRequest,
    PortfolioResponse,
    RenamePortfolioRequest,
)
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.portfolio_service import (
    archive_portfolio,
    create_portfolio,
    delete_portfolio,
    get_portfolio_by_id,
    list_portfolios,
    rename_portfolio,
    restore_portfolio,
)

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Portfolio not found.",
)


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: CreatePortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Create a new active portfolio. Returns 409 if the active-portfolio limit is reached."""
    try:
        portfolio = await create_portfolio(
            db,
            user_id=current_user.id,
            name=body.name,
            base_currency=body.base_currency,
        )
    except ValueError as exc:
        raise _conflict(str(exc))
    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse.model_validate(portfolio)


@router.get("", response_model=list[PortfolioResponse])
async def list_all(
    include_archived: bool = Query(default=False, description="Set to true to include archived portfolios."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PortfolioResponse]:
    """List portfolios for the current user. Active only by default."""
    portfolios = await list_portfolios(db, current_user.id, include_archived=include_archived)
    return [PortfolioResponse.model_validate(p) for p in portfolios]


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_one(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Return a single portfolio by ID."""
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND
    return PortfolioResponse.model_validate(portfolio)


@router.patch("/{portfolio_id}", response_model=PortfolioResponse)
async def rename(
    portfolio_id: UUID,
    body: RenamePortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Rename an active portfolio. Returns 409 if the portfolio is archived."""
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND
    try:
        portfolio = await rename_portfolio(db, portfolio, name=body.name)
    except ValueError as exc:
        raise _conflict(str(exc))
    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse.model_validate(portfolio)


@router.post("/{portfolio_id}/archive", response_model=PortfolioResponse)
async def archive(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Archive an active portfolio (soft-delete). Returns 409 if already archived."""
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND
    try:
        portfolio = await archive_portfolio(db, portfolio)
    except ValueError as exc:
        raise _conflict(str(exc))
    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse.model_validate(portfolio)


@router.post("/{portfolio_id}/restore", response_model=PortfolioResponse)
async def restore(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """Restore an archived portfolio. Returns 409 if active limit would be exceeded."""
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND
    try:
        portfolio = await restore_portfolio(db, portfolio, current_user.id)
    except ValueError as exc:
        raise _conflict(str(exc))
    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse.model_validate(portfolio)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Permanently delete an archived portfolio and all its data. Returns 409 if active."""
    portfolio = await get_portfolio_by_id(db, portfolio_id, current_user.id)
    if portfolio is None:
        raise _NOT_FOUND
    try:
        await delete_portfolio(db, portfolio)
    except ValueError as exc:
        raise _conflict(str(exc))
    await db.commit()
