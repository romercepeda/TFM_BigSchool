"""Pydantic schemas for the Data providers Settings section — Spec D12 §7, Changeset C04 §5."""

from pydantic import BaseModel


class ProviderKeyStatus(BaseModel):
    """API key status for one provider (D12 §7.3) — never the plaintext value."""

    provider: str
    display_name: str
    requires_api_key: bool
    configured: bool
    masked_key: str | None


class DataProvidersResponse(BaseModel):
    market_data_providers: list[str]
    market_data_available: list[str]
    fx_data_providers: list[str]
    fx_data_available: list[str]
    api_keys: list[ProviderKeyStatus]


class UpdateDataProvidersRequest(BaseModel):
    market_data_providers: list[str]
    fx_data_providers: list[str]
