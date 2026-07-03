"""Unit tests for the cascade-provider API key startup check — Spec D12 §10,
Changeset C04 §8.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig, validate_provider_api_keys

_ALL_KEYS = (
    "MARKET_DATA_TWELVE_DATA_API_KEY",
    "MARKET_DATA_EODHD_API_KEY",
    "MARKET_DATA_FINNHUB_API_KEY",
)


@pytest.fixture(autouse=True)
def _clear_provider_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_missing_key_for_configured_provider_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = AppConfig(market_data={"providers": ["twelve_data", "eodhd"]})
    monkeypatch.setenv("MARKET_DATA_TWELVE_DATA_API_KEY", "some-key")
    # MARKET_DATA_EODHD_API_KEY intentionally left unset.

    with pytest.raises(SystemExit) as exc_info:
        validate_provider_api_keys(cfg)

    assert exc_info.value.code == 1


def test_removing_provider_from_cascade_makes_startup_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppConfig(market_data={"providers": ["twelve_data"]})
    monkeypatch.setenv("MARKET_DATA_TWELVE_DATA_API_KEY", "some-key")
    # eodhd is not in the cascade — its key is allowed to remain unset.

    validate_provider_api_keys(cfg)  # must not raise


def test_all_keys_present_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = AppConfig(market_data={"providers": ["twelve_data", "eodhd", "finnhub"]})
    for key in _ALL_KEYS:
        monkeypatch.setenv(key, "some-key")

    validate_provider_api_keys(cfg)  # must not raise


def test_env_example_documents_the_eodhd_key() -> None:
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    assert "MARKET_DATA_EODHD_API_KEY" in env_example.read_text(encoding="utf-8")
