"""Data providers Settings API — Spec D12 §7, Changeset C04 §5.

GET   /settings/data-providers        — current cascade order + API key status
PUT   /settings/data-providers        — reorder/add/remove providers
POST  /settings/data-providers/reset  — restore the shipped default order (D12 §3)

All endpoints require system.view_config (D11 §5.1, administrator-only) — the
frontend hides the whole section for anyone without it (D12 §7.1), and these
dependencies are the actual enforcement layer.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.settings_schemas import (
    DataProvidersResponse,
    ProviderKeyStatus,
    UpdateDataProvidersRequest,
)
from app.auth.dependencies import get_current_user
from app.config import MARKET_DATA_PROVIDER_ENV_VARS, find_missing_provider_api_keys, get_config
from app.db.models.user import User
from app.db.session import get_db
from app.roles.dependencies import require_permission
from app.services import settings_overlay
from app.services.market_data.service import reset_market_data_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Shipped defaults (D12 §3) — restored by POST /settings/data-providers/reset.
_MARKET_DATA_DEFAULT = ["twelve_data", "eodhd", "finnhub"]
_FX_DATA_DEFAULT = ["frankfurter"]

_DISPLAY_NAMES = {
    "twelve_data": "Twelve Data",
    "eodhd": "EODHD",
    "finnhub": "Finnhub",
    "frankfurter": "Frankfurter",
}


def _mask_key(key: str) -> str:
    """Show only the last 6 characters (D12 §7.3), masking short keys entirely."""
    if len(key) <= 6:
        return "•" * len(key)
    return "•" * (len(key) - 6) + key[-6:]


def _api_key_statuses() -> list[ProviderKeyStatus]:
    statuses = [
        ProviderKeyStatus(
            provider=provider,
            display_name=_DISPLAY_NAMES[provider],
            requires_api_key=True,
            configured=bool(os.environ.get(env_var, "")),
            masked_key=_mask_key(value) if (value := os.environ.get(env_var, "")) else None,
        )
        for provider, env_var in MARKET_DATA_PROVIDER_ENV_VARS.items()
    ]
    # Frankfurter needs no key (D09 §3.2) — its entry omits one (D12 §7.3).
    statuses.append(
        ProviderKeyStatus(
            provider="frankfurter",
            display_name=_DISPLAY_NAMES["frankfurter"],
            requires_api_key=False,
            configured=True,
            masked_key=None,
        )
    )
    return statuses


def _current_state() -> DataProvidersResponse:
    cfg = get_config()
    return DataProvidersResponse(
        market_data_providers=settings_overlay.get_market_data_providers(
            cfg.market_data.providers
        ),
        market_data_available=list(MARKET_DATA_PROVIDER_ENV_VARS),
        fx_data_providers=settings_overlay.get_fx_data_providers(cfg.fx_data.providers),
        fx_data_available=_FX_DATA_DEFAULT,
        api_keys=_api_key_statuses(),
    )


def _validate_provider_lists(body: UpdateDataProvidersRequest) -> None:
    known_market = set(MARKET_DATA_PROVIDER_ENV_VARS)
    unknown_market = [p for p in body.market_data_providers if p not in known_market]
    if unknown_market:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown market data provider(s): {unknown_market}.",
        )
    unknown_fx = [p for p in body.fx_data_providers if p not in _FX_DATA_DEFAULT]
    if unknown_fx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown FX data provider(s): {unknown_fx}.",
        )
    if len(set(body.market_data_providers)) != len(body.market_data_providers):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="market_data_providers contains duplicate entries.",
        )

    missing = find_missing_provider_api_keys(body.market_data_providers)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot save — missing API key(s) for: "
                + ", ".join(f"{p} ({env})" for p, env in missing)
            ),
        )


@router.get(
    "/data-providers",
    response_model=DataProvidersResponse,
    dependencies=[Depends(require_permission("system.view_config"))],
)
async def get_data_providers() -> DataProvidersResponse:
    """Current cascade order for both lists, plus per-provider API key status."""
    return _current_state()


@router.put(
    "/data-providers",
    response_model=DataProvidersResponse,
    dependencies=[Depends(require_permission("system.view_config"))],
)
async def update_data_providers(
    body: UpdateDataProvidersRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DataProvidersResponse:
    """Reorder, add, or remove providers from either cascade list (D12 §7.2).

    Rejects unknown provider codes and any market data provider missing its
    API key — the same rule Spec D12 §10 enforces at startup, applied here
    so an admin can't save a broken configuration. An empty list is allowed
    (the frontend is responsible for its own confirmation dialog before
    sending that).
    """
    _validate_provider_lists(body)

    logger.info(
        "Settings: user %s updated data providers -> market_data=%s fx_data=%s",
        current_user.id, body.market_data_providers, body.fx_data_providers,
    )

    await settings_overlay.set_override(
        db,
        settings_overlay.MARKET_DATA_PROVIDERS_KEY,
        body.market_data_providers,
        updated_by_user_id=current_user.id,
    )
    await settings_overlay.set_override(
        db,
        settings_overlay.FX_DATA_PROVIDERS_KEY,
        body.fx_data_providers,
        updated_by_user_id=current_user.id,
    )
    reset_market_data_service()

    return _current_state()


@router.post(
    "/data-providers/reset",
    response_model=DataProvidersResponse,
    dependencies=[Depends(require_permission("system.view_config"))],
)
async def reset_data_providers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DataProvidersResponse:
    """Restore the shipped default order for both lists (D12 §3, §7.2)."""
    logger.info("Settings: user %s reset data providers to shipped defaults.", current_user.id)

    await settings_overlay.reset_override(
        db,
        settings_overlay.MARKET_DATA_PROVIDERS_KEY,
        _MARKET_DATA_DEFAULT,
        updated_by_user_id=current_user.id,
    )
    await settings_overlay.reset_override(
        db,
        settings_overlay.FX_DATA_PROVIDERS_KEY,
        _FX_DATA_DEFAULT,
        updated_by_user_id=current_user.id,
    )
    reset_market_data_service()

    return _current_state()
