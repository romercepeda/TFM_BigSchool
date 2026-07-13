"""Unit tests for D07 AI extraction logic — Spec D07 §4.

Tests cover pure functions: JSON parsing, schema validation, metric-to-indicator mapping.
No DB, no external API calls needed.
"""

from __future__ import annotations

import json

import pytest

from app.services.ai_providers.base import AIProvider, ExtractionOutput, ExtractedMetrics


# ── Fixtures ─────────────────────────────────────────────────────────────────


_VALID_EXTRACTION = {
    "asset_match": True,
    "asset_match_notes": None,
    "report_date": "2024-03-31",
    "report_period_name": "Q1 2024",
    "metrics": {
        "per": 18.5,
        "per_basis": "GAAP",
        "roe": 0.14,
        "debt_ebitda": 2.3,
        "revenue_growth_yoy": 0.07,
        "analyst_sentiment": "bullish",
        "management_tone": "bullish",
        "fundamentals_signal": "mixed",
    },
    "executive_summary_es": "• Los ingresos crecieron un 7% interanual\n• El ROE mejoró al 14%\n• Balance sólido",
    "executive_summary_en": "• Revenue grew 7% YoY\n• ROE improved to 14%\n• Strong balance sheet",
    "global_signal": "bullish",
    "confidence_notes": None,
    "calculations_detail": {
        "per": "Used system.current_price=20.0 / eps_ttm=1.08 (PDF Q1 EPS ×4). GAAP.",
    },
    "data_provenance": {
        "current_price": {"source": "system", "timestamp": "2024-03-31"},
    },
}

_MINIMAL_VALID_EXTRACTION = {
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
    "executive_summary_es": "No se encontraron métricas específicas en el documento.",
    "executive_summary_en": "No specific metrics found in the document.",
    "global_signal": None,
    "confidence_notes": "Insufficient financial data.",
    "calculations_detail": None,
    "data_provenance": None,
}

_DUMMY_SCHEMA: dict = {}  # _parse_response uses Pydantic, not the JSON schema dict


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse(raw_text: str):
    return AIProvider._parse_response(raw_text, "test-model", "test-provider", _DUMMY_SCHEMA)


# ── Tests: JSON parsing ───────────────────────────────────────────────────────


class TestJsonParsing:
    def test_valid_json_parses_ok(self):
        result = _parse(json.dumps(_VALID_EXTRACTION))
        assert result.parse_status == "ok"
        assert result.succeeded is True
        assert result.parsed_json == _VALID_EXTRACTION

    def test_json_in_markdown_fence_is_stripped(self):
        raw = f"```json\n{json.dumps(_VALID_EXTRACTION)}\n```"
        result = _parse(raw)
        assert result.parse_status == "ok"
        assert result.succeeded is True

    def test_json_in_plain_fence_is_stripped(self):
        raw = f"```\n{json.dumps(_VALID_EXTRACTION)}\n```"
        result = _parse(raw)
        assert result.parse_status == "ok"

    def test_invalid_json_returns_parse_error(self):
        result = _parse("This is not JSON at all.")
        assert result.parse_status == "invalid_json"
        assert result.succeeded is False
        assert result.parsed_json is None

    def test_empty_string_returns_parse_error(self):
        result = _parse("")
        assert result.parse_status == "invalid_json"

    def test_raw_response_preserved_on_error(self):
        raw = "BAD DATA"
        result = _parse(raw)
        assert result.raw_response == raw


# ── Tests: Schema validation ─────────────────────────────────────────────────


class TestSchemaValidation:
    def test_all_nulls_is_valid(self):
        result = _parse(json.dumps(_MINIMAL_VALID_EXTRACTION))
        assert result.parse_status == "ok"
        assert result.succeeded is True

    def test_missing_metrics_key_fails(self):
        bad = dict(_VALID_EXTRACTION)
        del bad["metrics"]
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"
        assert result.succeeded is False

    def test_missing_executive_summary_es_fails(self):
        bad = dict(_VALID_EXTRACTION)
        del bad["executive_summary_es"]
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"

    def test_missing_executive_summary_en_fails(self):
        bad = dict(_VALID_EXTRACTION)
        del bad["executive_summary_en"]
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"

    def test_invalid_global_signal_enum_fails(self):
        bad = {**_VALID_EXTRACTION, "global_signal": "strong_buy"}
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"

    def test_invalid_analyst_sentiment_enum_fails(self):
        bad = {
            **_VALID_EXTRACTION,
            "metrics": {**_VALID_EXTRACTION["metrics"], "analyst_sentiment": "neutral"},
        }
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"

    def test_partial_metrics_null_is_valid(self):
        partial = {
            **_VALID_EXTRACTION,
            "metrics": {
                "per": 22.0,
                "roe": None,
                "debt_ebitda": None,
                "revenue_growth_yoy": 0.05,
                "analyst_sentiment": "mixed",
            },
        }
        result = _parse(json.dumps(partial))
        assert result.parse_status == "ok"

    def test_list_value_in_per_fails(self):
        # Pydantic coerces str→float (acceptable) but never list→float.
        bad = {
            **_VALID_EXTRACTION,
            "metrics": {**_VALID_EXTRACTION["metrics"], "per": [18, 5]},
        }
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"


# ── Tests: asset_match (Changeset C05 — file/asset correspondence check) ─────


class TestAssetMatch:
    def test_matching_asset_parses_ok(self):
        result = _parse(json.dumps(_VALID_EXTRACTION))
        assert result.succeeded is True
        assert result.parsed_json["asset_match"] is True

    def test_mismatched_asset_still_parses_but_flagged_false(self):
        mismatch = {
            **_VALID_EXTRACTION,
            "asset_match": False,
            "asset_match_notes": "This document is a quarterly report for Microsoft Corporation.",
            "metrics": {k: None for k in _VALID_EXTRACTION["metrics"]},
        }
        result = _parse(json.dumps(mismatch))
        assert result.parse_status == "ok"
        assert result.parsed_json["asset_match"] is False
        assert "Microsoft" in result.parsed_json["asset_match_notes"]

    def test_missing_asset_match_defaults_to_true(self):
        # Backward compatibility: older/legacy responses without the field
        # are treated as a match rather than blocking the pipeline.
        legacy = dict(_VALID_EXTRACTION)
        del legacy["asset_match"]
        del legacy["asset_match_notes"]
        output = ExtractionOutput.model_validate(legacy)
        assert output.asset_match is True

    def test_invalid_asset_match_type_fails(self):
        bad = {**_VALID_EXTRACTION, "asset_match": "maybe"}
        result = _parse(json.dumps(bad))
        assert result.parse_status == "schema_error"


# ── Tests: report_period_name (Changeset C05 §3) ──────────────────────────────


class TestReportPeriodName:
    def test_present_name_parses(self):
        output = ExtractionOutput.model_validate(_VALID_EXTRACTION)
        assert output.report_period_name == "Q1 2024"

    def test_null_name_is_valid(self):
        extraction = {**_VALID_EXTRACTION, "report_period_name": None}
        output = ExtractionOutput.model_validate(extraction)
        assert output.report_period_name is None

    def test_missing_name_defaults_to_null(self):
        legacy = dict(_VALID_EXTRACTION)
        del legacy["report_period_name"]
        output = ExtractionOutput.model_validate(legacy)
        assert output.report_period_name is None

    def test_non_standard_name_passes_through(self):
        extraction = {**_VALID_EXTRACTION, "report_period_name": "Interim update — March 2026"}
        output = ExtractionOutput.model_validate(extraction)
        assert output.report_period_name == "Interim update — March 2026"


# ── Tests: Pydantic ExtractionOutput model ────────────────────────────────────


class TestExtractionOutputModel:
    def test_full_valid_extraction_validates(self):
        output = ExtractionOutput.model_validate(_VALID_EXTRACTION)
        assert output.global_signal == "bullish"
        assert output.metrics.per == pytest.approx(18.5)
        assert output.metrics.analyst_sentiment == "bullish"

    def test_all_null_validates(self):
        output = ExtractionOutput.model_validate(_MINIMAL_VALID_EXTRACTION)
        assert output.metrics.per is None
        assert output.global_signal is None

    def test_report_date_string_passes_through(self):
        output = ExtractionOutput.model_validate(_VALID_EXTRACTION)
        assert output.report_date == "2024-03-31"


# ── Tests: ai_extraction_key → indicator mapping ─────────────────────────────


class TestIndicatorKeyMapping:
    """Verify that ai_extraction_key values from the indicator catalog are all
    present as fields in ExtractedMetrics. ExtractedMetrics may carry additional
    metadata fields (per_basis, management_tone, fundamentals_signal) that are
    not catalog keys — the subset check is intentional.
    """

    # Keys that map to ai_extraction_key entries in indicators_catalog.yaml
    _CATALOG_KEYS = {"per", "roe", "debt_ebitda", "revenue_growth_yoy", "analyst_sentiment"}

    def test_catalog_keys_are_subset_of_model_fields(self):
        model_fields = set(ExtractedMetrics.model_fields.keys())
        assert self._CATALOG_KEYS.issubset(model_fields), (
            f"Missing catalog keys in ExtractedMetrics: {self._CATALOG_KEYS - model_fields}"
        )

    def test_all_catalog_keys_present_in_valid_extraction(self):
        metrics = _VALID_EXTRACTION["metrics"]
        for key in self._CATALOG_KEYS:
            assert key in metrics, f"Key '{key}' missing from extraction fixture"

    def test_quantitative_keys_accept_floats(self):
        quantitative = {"per", "roe", "debt_ebitda", "revenue_growth_yoy"}
        metrics = _VALID_EXTRACTION["metrics"]
        for key in quantitative:
            assert isinstance(metrics[key], (int, float)), f"{key} should be numeric"

    def test_qualitative_key_accepts_enum_values(self):
        for val in ("bullish", "mixed", "bearish"):
            m = ExtractedMetrics.model_validate(
                {**_VALID_EXTRACTION["metrics"], "analyst_sentiment": val}
            )
            assert m.analyst_sentiment == val
