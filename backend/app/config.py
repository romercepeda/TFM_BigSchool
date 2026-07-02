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
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# ── Sub-models (one per top-level config section) ────────────────────────────


class PortfoliosConfig(BaseModel):
    max_active_per_user: int = 10
    name_max_length: int = 60


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


class MarketDataConfig(BaseModel):
    provider: Literal["twelve_data", "finnhub"] = "twelve_data"
    twelve_data: TwelveDataConfig = TwelveDataConfig()
    finnhub: FinnhubConfig = FinnhubConfig()


class FrankfurterConfig(BaseModel):
    base_url: str = "https://api.frankfurter.dev/v2"


class FxDataConfig(BaseModel):
    provider: Literal["frankfurter"] = "frankfurter"
    frankfurter: FrankfurterConfig = FrankfurterConfig()


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
