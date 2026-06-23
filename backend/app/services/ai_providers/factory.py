"""AI provider factory — Spec D07 §3.3.

Resolves the configured ai.provider to the matching adapter at runtime.
Raises NonRetryableError if the API key is missing for the active provider.
"""

from __future__ import annotations

import os

from app.config import AppConfig
from app.services.ai_providers.base import AIProvider


class NonRetryableError(Exception):
    """Missing API key or unknown provider — do not retry (Spec D07 §7)."""


def get_ai_provider(cfg: AppConfig) -> AIProvider:
    """Instantiate the adapter for the active provider from config.

    Raises NonRetryableError if the active provider's API key is not set.
    """
    provider_name = cfg.ai.provider
    timeout = cfg.ai.per_call_timeout_seconds

    if provider_name == "anthropic":
        api_key = os.environ.get("AI_ANTHROPIC_API_KEY", "")
        if not api_key:
            raise NonRetryableError(
                "AI_ANTHROPIC_API_KEY is not set — cannot run Anthropic analysis."
            )
        from app.services.ai_providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=api_key,
            model=cfg.ai.anthropic.model,
            timeout=timeout,
        )

    if provider_name == "openai":
        api_key = os.environ.get("AI_OPENAI_API_KEY", "")
        if not api_key:
            raise NonRetryableError(
                "AI_OPENAI_API_KEY is not set — cannot run OpenAI analysis."
            )
        from app.services.ai_providers.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=api_key,
            model=cfg.ai.openai.model,
            timeout=timeout,
        )

    if provider_name == "gemini":
        api_key = os.environ.get("AI_GEMINI_API_KEY", "")
        if not api_key:
            raise NonRetryableError(
                "AI_GEMINI_API_KEY is not set — cannot run Gemini analysis."
            )
        from app.services.ai_providers.gemini_provider import GeminiProvider
        return GeminiProvider(
            api_key=api_key,
            model=cfg.ai.gemini.model,
            timeout=timeout,
        )

    raise NonRetryableError(f"Unknown AI provider: {provider_name!r}")
