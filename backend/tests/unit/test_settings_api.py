"""Unit tests for the Data providers Settings API's pure logic — Spec D12 §7,
Changeset C04 §5. DB-touching paths (persist/reset) were verified manually
against the real dev database; these cover masking and validation only.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.settings import _mask_key, _validate_provider_lists
from app.api.settings_schemas import UpdateDataProvidersRequest

_ALL_KEYS = (
    "MARKET_DATA_TWELVE_DATA_API_KEY",
    "MARKET_DATA_EODHD_API_KEY",
    "MARKET_DATA_FINNHUB_API_KEY",
)


@pytest.fixture(autouse=True)
def _set_all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ALL_KEYS:
        monkeypatch.setenv(key, "some-real-key-value")


# ── Masking (D12 §7.3) ─────────────────────────────────────────────────────────


def test_mask_key_shows_only_last_six_chars() -> None:
    assert _mask_key("abcdefgh1234") == "••••••gh1234"


def test_mask_key_masks_entire_short_key() -> None:
    assert _mask_key("abc") == "•••"


def test_mask_key_exactly_six_chars_fully_masked() -> None:
    # len <= 6 masks everything rather than showing the whole key unmasked.
    assert _mask_key("abcdef") == "••••••"


# ── Validation ──────────────────────────────────────────────────────────────────


def test_validate_rejects_unknown_market_data_provider() -> None:
    body = UpdateDataProvidersRequest(
        market_data_providers=["twelve_data", "not_real"], fx_data_providers=["frankfurter"]
    )
    with pytest.raises(HTTPException) as exc_info:
        _validate_provider_lists(body)
    assert exc_info.value.status_code == 400


def test_validate_rejects_unknown_fx_data_provider() -> None:
    body = UpdateDataProvidersRequest(
        market_data_providers=["twelve_data"], fx_data_providers=["not_real"]
    )
    with pytest.raises(HTTPException) as exc_info:
        _validate_provider_lists(body)
    assert exc_info.value.status_code == 400


def test_validate_rejects_duplicate_market_data_providers() -> None:
    body = UpdateDataProvidersRequest(
        market_data_providers=["twelve_data", "twelve_data"], fx_data_providers=["frankfurter"]
    )
    with pytest.raises(HTTPException) as exc_info:
        _validate_provider_lists(body)
    assert exc_info.value.status_code == 400


def test_validate_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_DATA_EODHD_API_KEY", raising=False)
    body = UpdateDataProvidersRequest(
        market_data_providers=["twelve_data", "eodhd"], fx_data_providers=["frankfurter"]
    )
    with pytest.raises(HTTPException) as exc_info:
        _validate_provider_lists(body)
    assert exc_info.value.status_code == 400
    assert "eodhd" in exc_info.value.detail


def test_validate_accepts_valid_list() -> None:
    body = UpdateDataProvidersRequest(
        market_data_providers=["eodhd", "twelve_data", "finnhub"],
        fx_data_providers=["frankfurter"],
    )
    _validate_provider_lists(body)  # must not raise


def test_validate_accepts_empty_market_data_list() -> None:
    """D12 §7.2 — emptying the list is allowed; the frontend owns the confirm dialog."""
    body = UpdateDataProvidersRequest(market_data_providers=[], fx_data_providers=["frankfurter"])
    _validate_provider_lists(body)  # must not raise
