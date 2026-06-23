"""AI provider abstraction layer — Spec D07 §3.

Defines the shared AIProvider interface and the AIExtractionResult return type.
Each concrete adapter (Anthropic, OpenAI, Gemini) implements AIProvider.

Pydantic model ExtractionOutput mirrors ai_extraction_schema.json exactly;
it is the authoritative in-code schema used for response validation.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ValidationError


# ── Pydantic model matching ai_extraction_schema.json §4.2 ───────────────────


class ExtractedMetrics(BaseModel):
    per: float | None = None
    roe: float | None = None
    debt_ebitda: float | None = None
    revenue_growth_yoy: float | None = None
    analyst_sentiment: Literal["bullish", "mixed", "bearish"] | None = None


class ExtractionOutput(BaseModel):
    report_date: str | None = None
    metrics: ExtractedMetrics
    executive_summary: str
    global_signal: Literal["bullish", "neutral", "bearish"] | None = None
    confidence_notes: str | None = None


# ── Structured result returned by every adapter ───────────────────────────────


@dataclass
class AIExtractionResult:
    parsed_json: dict | None
    raw_response: str
    provider: str
    model_version: str
    parse_status: Literal["ok", "invalid_json", "schema_error"]
    error: str | None = field(default=None)

    @property
    def succeeded(self) -> bool:
        return self.parse_status == "ok" and self.parsed_json is not None


# ── Abstract provider interface ───────────────────────────────────────────────


class AIProvider(ABC):
    """All AI adapters implement this interface."""

    @abstractmethod
    async def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        prompt_template: str,
        schema: dict,
        asset_context: dict,
    ) -> AIExtractionResult:
        """Analyze a PDF and return structured extraction result.

        Args:
            pdf_bytes: Raw bytes of the uploaded PDF.
            prompt_template: Contents of ai_extraction_prompt.md with {placeholder} vars.
            schema: Parsed ai_extraction_schema.json (for embedding in prompt).
            asset_context: Dict with keys ticker, name, asset_type, quote_currency.

        Returns:
            AIExtractionResult. On parse failure, parse_status is not "ok".
        """

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_full_prompt(prompt_template: str, schema: dict, asset_context: dict) -> str:
        """Format the prompt template with asset context and append the JSON schema."""
        formatted = prompt_template.format(**asset_context)
        schema_json = json.dumps(schema, indent=2)
        return formatted + f"\n\n---\nExtraction Schema (JSON Schema):\n\n```json\n{schema_json}\n```"

    @staticmethod
    def _parse_response(
        raw_text: str,
        model_version: str,
        provider_name: str,
        schema: dict,
    ) -> AIExtractionResult:
        """Extract JSON from raw LLM text, validate with Pydantic, return result."""
        # Strip markdown code fences if the LLM wrapped the JSON
        text = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if fence_match:
            text = fence_match.group(1).strip()

        # Parse JSON
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return AIExtractionResult(
                parsed_json=None,
                raw_response=raw_text,
                provider=provider_name,
                model_version=model_version,
                parse_status="invalid_json",
                error=str(exc),
            )

        # Validate with Pydantic (mirrors ai_extraction_schema.json)
        try:
            ExtractionOutput.model_validate(parsed)
        except ValidationError as exc:
            return AIExtractionResult(
                parsed_json=parsed,
                raw_response=raw_text,
                provider=provider_name,
                model_version=model_version,
                parse_status="schema_error",
                error=exc.json(),
            )

        return AIExtractionResult(
            parsed_json=parsed,
            raw_response=raw_text,
            provider=provider_name,
            model_version=model_version,
            parse_status="ok",
        )
