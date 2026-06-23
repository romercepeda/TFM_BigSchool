"""Google Gemini adapter — Spec D07 §3.2.

Uses the google-genai SDK with inline PDF data (native support, no text extraction).
The synchronous client is wrapped in asyncio.to_thread for non-blocking operation.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.services.ai_providers.base import AIExtractionResult, AIProvider

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "gemini"


class NonRetryableError(Exception):
    """Config or auth error — should not be retried (Spec D07 §7)."""


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        # Import lazily so the package is optional until the provider is active
        from google import genai  # type: ignore[import-untyped]

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        prompt_template: str,
        schema: dict,
        asset_context: dict,
    ) -> AIExtractionResult:
        full_prompt = self._build_full_prompt(prompt_template, schema, asset_context)

        try:
            raw_text = await asyncio.wait_for(
                asyncio.to_thread(self._sync_generate, pdf_bytes, full_prompt),
                timeout=self._timeout,
            )
        except Exception as exc:
            # Distinguish auth/config errors from transient ones
            err = str(exc).lower()
            if "api key" in err or "invalid" in err or "permission" in err:
                raise NonRetryableError(f"Gemini config error: {exc}") from exc
            raise

        logger.info("Gemini %s completed: %d chars extracted.", self._model, len(raw_text))
        return self._parse_response(raw_text, self._model, _PROVIDER_NAME, schema)

    def _sync_generate(self, pdf_bytes: bytes, prompt: str) -> str:
        from google.genai import types  # type: ignore[import-untyped]

        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                types.Part.from_text(text=prompt),
            ],
        )
        return response.text or ""
