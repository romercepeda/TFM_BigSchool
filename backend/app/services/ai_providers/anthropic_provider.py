"""Anthropic Claude adapter — Spec D07 §3.2.

Uses the official anthropic SDK with AsyncAnthropic for non-blocking calls.
PDF is attached as a base64 document block (native support — no text extraction needed).
Adaptive thinking is enabled for Opus 4.x models (§3 guidance).
"""

from __future__ import annotations

import asyncio
import base64
import logging

import anthropic

from app.services.ai_providers.base import AIExtractionResult, AIProvider

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "anthropic"


class NonRetryableError(Exception):
    """Config or auth error — should not be retried (Spec D07 §7)."""


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        prompt_template: str,
        schema: dict,
        asset_context: dict,
    ) -> AIExtractionResult:
        b64_pdf = base64.standard_b64encode(pdf_bytes).decode()
        system_text = self._build_full_prompt(prompt_template, schema, asset_context)

        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=8192,
                    thinking={"type": "adaptive"},
                    system=system_text,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": b64_pdf,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "Please analyze this financial report and return "
                                        "the JSON object as specified."
                                    ),
                                },
                            ],
                        }
                    ],
                ),
                timeout=self._timeout,
            )
        except anthropic.AuthenticationError as exc:
            raise NonRetryableError(f"Anthropic authentication failed: {exc}") from exc
        except anthropic.NotFoundError as exc:
            raise NonRetryableError(f"Anthropic model not found: {exc}") from exc
        except Exception:
            raise  # retryable — let the Celery task handle it

        # Extract text blocks (adaptive thinking may also produce thinking blocks)
        raw_text = "".join(
            block.text
            for block in response.content
            if hasattr(block, "text") and block.type == "text"
        )
        model_used = response.model or self._model
        logger.info("Anthropic %s completed: %d chars extracted.", model_used, len(raw_text))
        return self._parse_response(raw_text, model_used, _PROVIDER_NAME, schema)
