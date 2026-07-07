"""Application configuration loader.

Loads config.yaml at startup and validates it against a typed schema (Pydantic).
The application refuses to start if the file is missing, invalid YAML, or fails
schema validation — per Spec 00f §4 (fail-fast policy).

Usage:
    from app.config import get_config
    config = get_config()
    limit = config.portfolios.max_active_per_user
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)


def _migrate_singular_provider_key(data: object, *, section: str) -> object:
    """Back-compat shim for the deprecated singular `provider` key (Spec D12 §9,

    Changeset C04 §7). If `provider` is present and `providers` is not, build a
    single-element list from it. If both are present, the new key wins.
    Removed entirely in the next major release.
    """
    if not isinstance(data, dict):
        return data
    has_old = "provider" in data
    has_new = "providers" in data
    if has_old and has_new:
        logger.warning(
            "config.yaml: both '%s.provider' (deprecated) and '%s.providers' are "
            "set — using 'providers' and ignoring the deprecated 'provider' key.",
            section, section,
        )
    elif has_old and not has_new:
        logger.warning(
            "config.yaml: '%s.provider' is deprecated — use '%s.providers' (a "
            "list) instead. Treating it as providers=[%r] for this run.",
            section, section, data["provider"],
        )
        data = {**data, "providers": [data["provider"]]}
    return data

# ── Sub-models (one per top-level config section) ────────────────────────────


class PortfoliosConfig(BaseModel):
    max_active_per_user: int = 10
    name_max_length: int = 60


class PortfolioSummaryConfig(BaseModel):
    """Changeset C08 §5/§9 — the in-memory portfolioHeader cache. 0 disables caching."""

    cache_ttl_seconds: int = Field(default=300, ge=0)


class PortfolioPerformanceConfig(BaseModel):
    """Changeset C08 §9 — added ahead of the future D14 Sharpe ratio work, not

    consumed by C08 itself. Decimal (not float) per Spec D04 §3.2, since this
    value will eventually feed a Decimal-only calculation.
    """

    risk_free_rate: Decimal = Field(default=Decimal("0.03"), ge=0, le=Decimal("0.20"))


class PortfolioConfig(BaseModel):
    """Singular `portfolio:` section (Changeset C08) — deliberately separate

    from the existing plural `portfolios:` section (Spec D02's per-user
    limits) rather than nested inside it, per the changeset's own §9 table.
    """

    summary: PortfolioSummaryConfig = PortfolioSummaryConfig()
    performance: PortfolioPerformanceConfig = PortfolioPerformanceConfig()


class UploadsConfig(BaseModel):
    max_file_size_mb: int = 20


class AuthMethodConfig(BaseModel):
    enabled: bool = True


class AuthMethodsConfig(BaseModel):
    google: AuthMethodConfig = AuthMethodConfig()
    microsoft: AuthMethodConfig = AuthMethodConfig()
    password: AuthMethodConfig = AuthMethodConfig()
    guest: AuthMethodConfig = AuthMethodConfig()


class AuthenticationConfig(BaseModel):
    methods: AuthMethodsConfig = AuthMethodsConfig()


class IndicatorsScheduledJobConfig(BaseModel):
    daily_run_hour_utc: int = 2


class IndicatorsConfig(BaseModel):
    scheduled_job: IndicatorsScheduledJobConfig = IndicatorsScheduledJobConfig()


class AlertsConfig(BaseModel):
    near_crossing_pct: float = 0.03


class AnthropicAiConfig(BaseModel):
    model: str = "claude-opus-4-7"


class OpenAiConfig(BaseModel):
    model: str = "gpt-4o"


class GeminiAiConfig(BaseModel):
    model: str = "gemini-2.5-pro"


class AiNotificationsConfig(BaseModel):
    poll_interval_seconds: int = 30


class AiConfig(BaseModel):
    provider: Literal["anthropic", "openai", "gemini"] = "anthropic"
    anthropic: AnthropicAiConfig = AnthropicAiConfig()
    openai: OpenAiConfig = OpenAiConfig()
    gemini: GeminiAiConfig = GeminiAiConfig()
    per_call_timeout_seconds: int = 120
    notifications: AiNotificationsConfig = AiNotificationsConfig()


class I18nConfig(BaseModel):
    default_language: str = "es"
    supported_languages: list[str] = ["es", "en"]


class TwelveDataConfig(BaseModel):
    base_url: str = "https://api.twelvedata.com"
    daily_call_budget: int = 800


class FinnhubConfig(BaseModel):
    base_url: str = "https://finnhub.io/api/v1"
    per_minute_call_budget: int = 60


class EODHDConfig(BaseModel):
    """Spec D12 §4/§9 — configures the EODHD adapter for when it is wired

    into the cascade (Changeset C04 §2); this is not yet the case behind
    `USE_CASCADE=false`.
    """

    base_url: str = "https://eodhd.com/api"
    daily_call_budget: int = 20
    max_lookback_days: int = 365


class MarketDataConfig(BaseModel):
    """Spec D12 §9 — `providers` (ordered cascade) replaces D09's singular

    `provider`. The deprecated singular key still loads for one release via
    `_migrate_singular_provider_key` (Changeset C04 §7).
    """

    providers: list[Literal["twelve_data", "eodhd", "finnhub"]] = [
        "twelve_data", "eodhd", "finnhub",
    ]
    # Spec D12 §6.3 — how long CascadeFailureReport rows are kept before a
    # cleanup pass hard-deletes them. Operational data, not the audit log.
    failure_report_retention_days: int = Field(default=30, ge=1)
    twelve_data: TwelveDataConfig = TwelveDataConfig()
    finnhub: FinnhubConfig = FinnhubConfig()
    eodhd: EODHDConfig = EODHDConfig()

    @model_validator(mode="before")
    @classmethod
    def _migrate_provider_key(cls, data: object) -> object:
        return _migrate_singular_provider_key(data, section="market_data")


class FrankfurterConfig(BaseModel):
    base_url: str = "https://api.frankfurter.dev/v2"


class FxDataConfig(BaseModel):
    """Spec D12 §9 — `providers` (ordered cascade) replaces D09's singular

    `provider`. In v1 this list has a single element (`frankfurter`) — the
    architectural mechanism is the same as market_data's cascade so that
    adding a second FX provider later is a configuration change (D12 §5.2).
    """

    providers: list[Literal["frankfurter"]] = ["frankfurter"]
    frankfurter: FrankfurterConfig = FrankfurterConfig()

    @model_validator(mode="before")
    @classmethod
    def _migrate_provider_key(cls, data: object) -> object:
        return _migrate_singular_provider_key(data, section="fx_data")


class SecurityConfig(BaseModel):
    """Spec D11 §11 — bootstrap administrator settings.

    default_admin_email is a plain str, not EmailStr: pydantic's EmailStr rejects
    the spec's own default (admin@portfolioia.local) as a reserved/non-routable
    TLD. This is intentional — it's a bootstrap login identifier, not a mailbox.
    """

    default_admin_email: str = "admin@portfolioia.local"
    default_admin_password_length: int = Field(default=24, ge=16, le=64)


# ── Root config model ─────────────────────────────────────────────────────────


class AppConfig(BaseModel):
    """Root configuration object. Available via get_config() throughout the app."""

    portfolios: PortfoliosConfig = PortfoliosConfig()
    portfolio: PortfolioConfig = PortfolioConfig()
    uploads: UploadsConfig = UploadsConfig()
    authentication: AuthenticationConfig = AuthenticationConfig()
    indicators: IndicatorsConfig = IndicatorsConfig()
    alerts: AlertsConfig = AlertsConfig()
    ai: AiConfig = AiConfig()
    i18n: I18nConfig = I18nConfig()
    market_data: MarketDataConfig = MarketDataConfig()
    fx_data: FxDataConfig = FxDataConfig()
    security: SecurityConfig = SecurityConfig()


# ── Loader ────────────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_config: AppConfig | None = None


def load_config(path: Path = _CONFIG_PATH) -> AppConfig:
    """Load and validate config.yaml. Raises on any error (fail-fast per Spec 00f §4).

    Args:
        path: Path to the YAML configuration file. Defaults to config.yaml next to backend/.

    Returns:
        Validated AppConfig instance.

    Raises:
        SystemExit: if the file is missing, unreadable, invalid YAML, or fails schema validation.
    """
    if not path.exists():
        logger.critical("config.yaml not found at %s — cannot start.", path)
        raise SystemExit(1)

    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        logger.critical("config.yaml is not valid YAML: %s", exc)
        raise SystemExit(1) from exc

    try:
        return AppConfig(**raw)
    except ValidationError as exc:
        logger.critical("config.yaml failed schema validation:\n%s", exc)
        raise SystemExit(1) from exc


def get_config() -> AppConfig:
    """Return the cached application config. Call load_config() first at startup."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


# ── Startup validation: cascade providers must have their API key set ────────
# Spec D12 §10 / Changeset C04 §8. Frankfurter (the only fx_data provider)
# needs no key (Spec D09 §3.2) and is not in this table.

# Public: also consulted by the Settings API (Changeset C04 §5) to display
# per-provider key status and to validate an admin's edit before saving it.
MARKET_DATA_PROVIDER_ENV_VARS: dict[str, str] = {
    "twelve_data": "MARKET_DATA_TWELVE_DATA_API_KEY",
    "eodhd": "MARKET_DATA_EODHD_API_KEY",
    "finnhub": "MARKET_DATA_FINNHUB_API_KEY",
}


def find_missing_provider_api_keys(providers: list[str]) -> list[tuple[str, str]]:
    """Return [(provider, missing_env_var), ...] for providers with no key set."""
    return [
        (provider, env_var)
        for provider in providers
        if (env_var := MARKET_DATA_PROVIDER_ENV_VARS.get(provider)) and not os.environ.get(env_var)
    ]


def validate_provider_api_keys(cfg: AppConfig, providers: list[str] | None = None) -> None:
    """Fail fast if a provider has no API key set.

    `providers` defaults to `cfg.market_data.providers`; callers that have
    an effective list overlaid with a DB override (Changeset C04 §5) should
    pass it explicitly so the check reflects what will actually run.

    Raises SystemExit(1), matching load_config()'s fail-fast style, rather
    than letting the gap surface later as a runtime ProviderError on the
    first daily job run.
    """
    missing = find_missing_provider_api_keys(
        providers if providers is not None else cfg.market_data.providers
    )
    if not missing:
        return

    for provider, env_var in missing:
        logger.critical(
            "Provider '%s' is configured in market_data.providers but its API "
            "key is missing; either set %s in .env or remove '%s' from the "
            "cascade in Settings.",
            provider, env_var, provider,
        )
    raise SystemExit(1)
