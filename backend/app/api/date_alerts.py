"""DateAlert API endpoints — Changeset C17.

All routes are nested under /portfolios/{portfolio_id}/holdings/{holding_id}/,
mirroring price_levels.py.

Endpoints:
    GET    .../date-alerts                — list alerts for a holding
    POST   .../date-alerts                — create one alert
    PATCH  .../date-alerts/{aid}          — edit an alert (always allowed)
    DELETE .../date-alerts/{aid}          — hard-delete
    POST   .../date-alerts/{aid}/mark-read — acknowledge a due alert
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.date_alert_schemas import DateAlertIn, DateAlertPatch, DateAlertResponse
from app.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services import date_alert_service as svc
from app.services.lot_service import get_holding_with_asset
from app.services.portfolio_service import get_portfolio_by_id

router = APIRouter(
    prefix="/portfolios/{portfolio_id}/holdings/{holding_id}/date-alerts",
    tags=["date-alerts"],
)

_NOT_FOUND_PORTFOLIO = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found."
)
_NOT_FOUND_HOLDING = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found."
)
_NOT_FOUND_ALERT = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Date alert not found."
)


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


# ── List ─────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[DateAlertResponse],
    dependencies=[Depends(require_permission("date_alert.view"))],
)
async def list_date_alerts(
    portfolio_id: UUID,
    holding_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DateAlertResponse]:
    await _require_holding(portfolio_id, holding_id, current_user, db)
    alerts = await svc.list_date_alerts(db, holding_id)
    return [DateAlertResponse.model_validate(a) for a in alerts]


# ── Create ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=DateAlertResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("date_alert.create"))],
)
async def create_date_alert(
    portfolio_id: UUID,
    holding_id: UUID,
    body: DateAlertIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DateAlertResponse:
    await _require_holding(portfolio_id, holding_id, current_user, db)

    alert = await svc.create_date_alert(
        db, holding_id, alert_date=body.alert_date, description=body.description
    )
    await db.commit()
    await db.refresh(alert)
    return DateAlertResponse.model_validate(alert)


# ── Edit ─────────────────────────────────────────────────────────────────────


@router.patch(
    "/{alert_id}",
    response_model=DateAlertResponse,
    dependencies=[Depends(require_permission("date_alert.edit"))],
)
async def edit_date_alert(
    portfolio_id: UUID,
    holding_id: UUID,
    alert_id: UUID,
    body: DateAlertPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DateAlertResponse:
    await _require_holding(portfolio_id, holding_id, current_user, db)

    alert = await svc.get_date_alert(db, alert_id, holding_id)
    if alert is None:
        raise _NOT_FOUND_ALERT

    alert = await svc.edit_date_alert(
        db, alert, alert_date=body.alert_date, description=body.description
    )
    await db.commit()
    await db.refresh(alert)
    return DateAlertResponse.model_validate(alert)


# ── Delete ───────────────────────────────────────────────────────────────────


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("date_alert.delete"))],
)
async def delete_date_alert(
    portfolio_id: UUID,
    holding_id: UUID,
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _require_holding(portfolio_id, holding_id, current_user, db)

    alert = await svc.get_date_alert(db, alert_id, holding_id)
    if alert is None:
        raise _NOT_FOUND_ALERT

    await svc.delete_date_alert(db, alert)
    await db.commit()


# ── Mark alert as read ────────────────────────────────────────────────────────


@router.post(
    "/{alert_id}/mark-read",
    response_model=DateAlertResponse,
    dependencies=[Depends(require_permission("date_alert.edit"))],
)
async def mark_alert_read(
    portfolio_id: UUID,
    holding_id: UUID,
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DateAlertResponse:
    """Acknowledge a due alert. Returns 409 if the alert is still 'pending'."""
    await _require_holding(portfolio_id, holding_id, current_user, db)

    alert = await svc.get_date_alert(db, alert_id, holding_id)
    if alert is None:
        raise _NOT_FOUND_ALERT

    try:
        alert = await svc.mark_alert_seen(db, alert)
    except ValueError as exc:
        raise _conflict(str(exc))

    await db.commit()
    await db.refresh(alert)
    return DateAlertResponse.model_validate(alert)
