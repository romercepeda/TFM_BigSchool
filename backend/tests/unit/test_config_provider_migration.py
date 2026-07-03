"""Unit tests for the market_data/fx_data `provider` -> `providers` migration
shim — Spec D12 §9, Changeset C04 §7.
"""

from __future__ import annotations

import logging

from app.config import AppConfig


def test_old_singular_key_only_builds_single_element_list(caplog) -> None:  # noqa: ANN001
    with caplog.at_level(logging.WARNING):
        cfg = AppConfig(market_data={"provider": "twelve_data"})

    assert cfg.market_data.providers == ["twelve_data"]
    assert any("deprecated" in r.message for r in caplog.records)


def test_new_list_key_only_loads_silently(caplog) -> None:  # noqa: ANN001
    with caplog.at_level(logging.WARNING):
        cfg = AppConfig(market_data={"providers": ["twelve_data", "eodhd"]})

    assert cfg.market_data.providers == ["twelve_data", "eodhd"]
    assert not any("deprecated" in r.message for r in caplog.records)


def test_both_keys_present_new_wins_and_warns(caplog) -> None:  # noqa: ANN001
    with caplog.at_level(logging.WARNING):
        cfg = AppConfig(
            market_data={"provider": "finnhub", "providers": ["twelve_data"]}
        )

    assert cfg.market_data.providers == ["twelve_data"]
    assert any("ignoring" in r.message for r in caplog.records)


def test_default_is_the_shipped_cascade_order() -> None:
    cfg = AppConfig()
    assert cfg.market_data.providers == ["twelve_data", "eodhd", "finnhub"]
    assert cfg.fx_data.providers == ["frankfurter"]


def test_fx_data_migration_shim_also_applies(caplog) -> None:  # noqa: ANN001
    with caplog.at_level(logging.WARNING):
        cfg = AppConfig(fx_data={"provider": "frankfurter"})

    assert cfg.fx_data.providers == ["frankfurter"]
    assert any("deprecated" in r.message for r in caplog.records)
