"""OpenAI GPT adapter — Spec D07 §3.2.

Sends PDF content as extracted text (OpenAI Chat Completions does not support
native PDF document blocks). Uses pypdf for extraction. JSON mode enforced via
response_format={"type": "json_object"}.
"""

from __future__ import annotations

import asyncio
import io
import logging

import pypdf
from openai import AsyncOpenAI, AuthenticationError, NotFoundError

from app.services.ai_providers.base import AIExtractionResult, AIProvider

logger = logging.getLogger(__name__)

_PROVIDER_NAME = "openai"
_MAX_TEXT_CHARS = 60_000  # hard cap to stay within context limits


class NonRetryableError(Exception):
    """Config or auth error — should not be retried (Spec D07 §7)."""


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str, timeout: int) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        prompt_template: str,
        schema: dict,
        asset_context: dict,
    ) -> AIExtractionResult:
        # Extract text in a thread pool (pypdf is synchronous)
        pdf_text = await asyncio.to_thread(self._extract_text, pdf_bytes)
        if not pdf_text.strip():
            raise ValueError("PDF text extraction yielded empty content.")

        system_text = self._build_full_prompt(prompt_template, schema, asset_context)

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_text},
                        {
                            "role": "user",
                            "content": (
                                f"Financial report text:\n\n{pdf_text[:_MAX_TEXT_CHARS]}"
                            ),
                        },
                    ],
                    response_format={"type": "json_object"},
                ),
                timeout=self._timeout,
            )
        except AuthenticationError as exc:
            raise NonRetryableError(f"OpenAI authentication failed: {exc}") from exc
        except NotFoundError as exc:
            raise NonRetryableError(f"OpenAI model not found: {exc}") from exc
        except Exception:
            raise

        raw_text = response.choices[0].message.content or ""
        model_used = response.model or self._model
        logger.info("OpenAI %s completed: %d chars extracted.", model_used, len(raw_text))
        return self._parse_response(raw_text, model_used, _PROVIDER_NAME, schema)

    @staticmethod
    def _extract_text(pdf_bytes: bytes) -> str:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
