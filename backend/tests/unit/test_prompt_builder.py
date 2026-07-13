"""Unit tests for the enriched prompt builder — Spec D07 context-enrichment.

Tests cover:
  1. Prompt built with full system context (price + historical indicators)
  2. Prompt built with only current price (no historical indicators)
  3. Prompt built with empty system context (falls back to legacy behaviour)
  4. JSON schema validation of new fields (per_basis, management_tone,
     fundamentals_signal, calculations_detail, data_provenance)

No DB, no external API calls.
"""

from __future__ import annotations

import json

import pytest

from app.services.ai_providers.base import AIProvider, ExtractionOutput, ExtractedMetrics


# ── Shared fixtures ───────────────────────────────────────────────────────────

_ASSET_CONTEXT = {
    "ticker": "INTC",
    "name": "Intel Corporation",
    "asset_type": "stock",
    "quote_currency": "USD",
}

_PROMPT_TEMPLATE = (
    "Ticker: {ticker}\nCurrency: {quote_currency}\n"
    "{system_data_block}"
    "Analyze the PDF.\n"
)

_DUMMY_SCHEMA: dict = {}


def _build(system_context: dict | None) -> str:
    return AIProvider._build_full_prompt(
        _PROMPT_TEMPLATE, _DUMMY_SCHEMA, _ASSET_CONTEXT, system_context
    )


# ── Test 1: full system context ───────────────────────────────────────────────


class TestPromptWithFullContext:
    """Prompt includes current_price AND historical indicators."""

    _SYSTEM_CTX = {
        "current_price": 21.45,
        "price_as_of": "2026-06-27",
        "quote_currency": "USD",
        "historical_indicators": [
            {"metric": "per", "value": 18.5, "as_of": "2026-03-31"},
            {"metric": "per", "value": 19.2, "as_of": "2025-12-31"},
            {"metric": "roe", "value": 0.23, "as_of": "2026-03-31"},
            {"metric": "debt_ebitda", "value": 2.1, "as_of": "2026-03-31"},
            {"metric": "revenue_growth_yoy", "value": 0.09, "as_of": "2026-03-31"},
        ],
    }

    def test_system_data_block_header_present(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "## System-Provided Data" in prompt

    def test_current_price_in_prompt(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "21.45 USD" in prompt
        assert "2026-06-27" in prompt

    def test_prior_per_in_prompt(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "prior_per" in prompt
        assert "18.5" in prompt

    def test_prior_roe_in_prompt(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "prior_roe" in prompt
        assert "0.23" in prompt

    def test_asset_context_placeholders_replaced(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "INTC" in prompt
        assert "USD" in prompt
        assert "{ticker}" not in prompt
        assert "{quote_currency}" not in prompt

    def test_system_data_block_placeholder_replaced(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "{system_data_block}" not in prompt


# ── Test 2: only current price ────────────────────────────────────────────────


class TestPromptWithPriceOnly:
    """System context has current_price but no historical indicators."""

    _SYSTEM_CTX = {
        "current_price": 21.45,
        "price_as_of": "2026-06-27",
        "quote_currency": "USD",
    }

    def test_system_block_appears(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "## System-Provided Data" in prompt

    def test_current_price_present(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "21.45 USD" in prompt

    def test_no_prior_metrics_rows(self):
        prompt = _build(self._SYSTEM_CTX)
        assert "prior_per" not in prompt
        assert "prior_roe" not in prompt


# ── Test 3: empty / no system context (legacy fallback) ──────────────────────


class TestPromptWithNoContext:
    """When system_context is None or {}, the block is absent and {system_data_block}
    is cleanly removed — identical behaviour to the pre-enrichment prompt builder."""

    def test_none_context_no_block(self):
        prompt = _build(None)
        assert "## System-Provided Data" not in prompt
        assert "{system_data_block}" not in prompt

    def test_empty_dict_no_block(self):
        prompt = _build({})
        assert "## System-Provided Data" not in prompt

    def test_asset_placeholders_still_replaced(self):
        prompt = _build(None)
        assert "INTC" in prompt
        assert "{ticker}" not in prompt

    def test_schema_suffix_always_appended(self):
        # _build_full_prompt always appends the schema; with dummy schema it serialises to '{}'
        prompt = _build(None)
        assert "Extraction Schema (JSON Schema)" in prompt


# ── Test 4: new schema fields validate correctly ──────────────────────────────


class TestNewSchemaFields:
    """Verify that ExtractionOutput and ExtractedMetrics accept the new fields."""

    _BASE_METRICS = {
        "per": 18.5,
        "per_basis": "GAAP",
        "roe": 0.14,
        "debt_ebitda": 2.3,
        "revenue_growth_yoy": 0.07,
        "analyst_sentiment": "bullish",
        "management_tone": "bullish",
        "fundamentals_signal": "mixed",
    }

    _FULL_OUTPUT = {
        "report_date": "2026-03-31",
        "metrics": _BASE_METRICS,
        "executive_summary_es": "• Ingresos suben un 7% interanual\n• Márgenes en expansión",
        "executive_summary_en": "• Revenue up 7% YoY\n• Margins expanding",
        "global_signal": "bullish",
        "confidence_notes": None,
        "calculations_detail": {
            "per": "price=21.45 (system, 2026-06-27) / eps_ttm=1.16 (PDF, Q1 diluted ×4). GAAP.",
            "roe": "net_income=1.5B / avg_equity=6.5B (PDF balance sheet). Quarterly ×4.",
            "debt_ebitda": "total_debt=12B / ebitda_gaap=5.8B. GAAP EBITDA = op_income+D&A.",
            "revenue_growth_yoy": "(12.7B - 11.7B) / 11.7B = 0.085. Prior year from PDF table.",
            "analyst_sentiment": "Management bullish on AI demand. Fundamentals mixed (margins up, revenue inline).",
        },
        "data_provenance": {
            "current_price": {"source": "system", "timestamp": "2026-06-27"},
            "eps_current_quarter": {"source": "pdf", "timestamp": "2026-03-31"},
            "revenue_prior_year": {"source": "pdf", "timestamp": "2025-03-31"},
        },
    }

    def test_full_output_with_new_fields_validates(self):
        output = ExtractionOutput.model_validate(self._FULL_OUTPUT)
        assert output.metrics.per_basis == "GAAP"
        assert output.metrics.management_tone == "bullish"
        assert output.metrics.fundamentals_signal == "mixed"
        assert isinstance(output.calculations_detail, dict)
        assert isinstance(output.data_provenance, dict)

    def test_new_fields_nullable(self):
        minimal = {
            "report_date": None,
            "metrics": {
                "per": None,
                "per_basis": None,
                "roe": None,
                "debt_ebitda": None,
                "revenue_growth_yoy": None,
                "analyst_sentiment": None,
                "management_tone": None,
                "fundamentals_signal": None,
            },
            "executive_summary_es": "Sin datos.",
            "executive_summary_en": "No data.",
            "global_signal": None,
            "confidence_notes": None,
            "calculations_detail": None,
            "data_provenance": None,
        }
        output = ExtractionOutput.model_validate(minimal)
        assert output.metrics.per_basis is None
        assert output.calculations_detail is None

    def test_invalid_per_basis_rejected(self):
        from pydantic import ValidationError
        bad = {**self._FULL_OUTPUT, "metrics": {**self._BASE_METRICS, "per_basis": "adjusted"}}
        with pytest.raises(ValidationError):
            ExtractionOutput.model_validate(bad)

    def test_invalid_management_tone_rejected(self):
        from pydantic import ValidationError
        bad = {**self._FULL_OUTPUT, "metrics": {**self._BASE_METRICS, "management_tone": "neutral"}}
        with pytest.raises(ValidationError):
            ExtractionOutput.model_validate(bad)
