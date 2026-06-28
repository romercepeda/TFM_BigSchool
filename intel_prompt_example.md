# Ejemplo de prompt completo — Intel Q4 2026
#
# Esto es EXACTAMENTE lo que la app envía a la IA junto con el PDF binario.
# Para probarlo en otra IA: adjunta el PDF y copia este texto como prompt.
#
# PDF: C:\Users\RomerCepeda\Downloads\intel Q4 2026 0000050863-26-000079.pdf
# ─────────────────────────────────────────────────────────────────────────────

You are a professional financial analyst. Analyze the attached financial report PDF and extract key metrics for the asset described below.

## Asset Context

- **Ticker**: INTC
- **Company / Name**: Intel Corporation
- **Asset Type**: stock
- **Quote Currency**: USD

## Instructions

1. Read the entire document carefully before extracting any data.
2. Extract each metric listed below. Use `null` for any field whose value cannot be confidently determined from the document.
3. Write a concise executive summary as 3–5 bullet points in the same language as the document (default to English if uncertain).
4. Determine the overall investment signal based on the report's full content.
5. **Return only a valid JSON object** — no preamble, no markdown code fences, no additional text outside the JSON.

## Metrics to Extract

- **per** (Price-to-Earnings Ratio): The trailing or reported P/E ratio as a plain number. Use `null` if not reported.
- **roe** (Return on Equity): As a decimal fraction (e.g., `0.15` for 15%). Use `null` if not reported.
- **debt_ebitda** (Debt/EBITDA): Leverage ratio as a plain number (e.g., `2.3`). Use `null` if not reported.
- **revenue_growth_yoy** (Revenue Growth YoY): Year-over-year growth as a decimal (e.g., `0.08` for +8%, `-0.05` for -5%). Use `null` if not reported.
- **analyst_sentiment**: The overall analyst or management tone from the document. One of `"bullish"`, `"mixed"`, or `"bearish"`. Use `null` if indeterminate.

## Global Signal Definition

- `"bullish"` — Strong positive outlook, improving fundamentals, confident management guidance.
- `"neutral"` — Mixed signals, moderate fundamentals, uncertain near-term direction.
- `"bearish"` — Deteriorating fundamentals, significant risks highlighted, negative outlook.
- `null` — Indeterminate; cannot assign a signal with confidence.

## Required Output Format

IMPORTANT: Return ONLY the JSON object below, nothing else. No markdown fences, no preamble, no explanation after the JSON.

{
  "report_date": "<YYYY-MM-DD or null>",
  "metrics": {
    "per": <number or null>,
    "roe": <number or null>,
    "debt_ebitda": <number or null>,
    "revenue_growth_yoy": <number or null>,
    "analyst_sentiment": "<bullish|mixed|bearish or null>"
  },
  "executive_summary": "<3-5 bullet points as a single string, each bullet on its own line starting with •>",
  "global_signal": "<bullish|neutral|bearish or null>",
  "confidence_notes": "<brief note on data quality or missing information, or null>"
}

---
Extraction Schema (JSON Schema):

{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AIExtractionOutput",
  "type": "object",
  "required": ["report_date", "metrics", "executive_summary", "global_signal"],
  "additionalProperties": false,
  "properties": {
    "report_date": {
      "description": "ISO 8601 date of the financial report, or null if not determinable",
      "oneOf": [
        { "type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$" },
        { "type": "null" }
      ]
    },
    "metrics": {
      "type": "object",
      "required": ["per", "roe", "debt_ebitda", "revenue_growth_yoy", "analyst_sentiment"],
      "additionalProperties": false,
      "properties": {
        "per": {
          "description": "Price-to-Earnings ratio (trailing or reported), or null",
          "oneOf": [{ "type": "number" }, { "type": "null" }]
        },
        "roe": {
          "description": "Return on Equity as a decimal fraction (e.g. 0.15 for 15%), or null",
          "oneOf": [{ "type": "number" }, { "type": "null" }]
        },
        "debt_ebitda": {
          "description": "Debt/EBITDA leverage ratio, or null",
          "oneOf": [{ "type": "number" }, { "type": "null" }]
        },
        "revenue_growth_yoy": {
          "description": "Year-over-year revenue growth as a decimal (e.g. 0.08 for +8%), or null",
          "oneOf": [{ "type": "number" }, { "type": "null" }]
        },
        "analyst_sentiment": {
          "description": "Overall analyst/management tone from the document",
          "oneOf": [
            { "type": "string", "enum": ["bullish", "mixed", "bearish"] },
            { "type": "null" }
          ]
        }
      }
    },
    "executive_summary": {
      "type": "string",
      "description": "3-5 bullet-point summary of the report's key findings"
    },
    "global_signal": {
      "description": "Overall investment signal derived from the report",
      "oneOf": [
        { "type": "string", "enum": ["bullish", "neutral", "bearish"] },
        { "type": "null" }
      ]
    },
    "confidence_notes": {
      "description": "Optional notes on data quality, missing fields, or confidence level",
      "oneOf": [{ "type": "string" }, { "type": "null" }]
    }
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# Respuesta esperada (ejemplo de formato válido que acepta la app):
#
# {
#   "report_date": "2026-01-24",
#   "metrics": {
#     "per": null,
#     "roe": -0.012,
#     "debt_ebitda": 4.2,
#     "revenue_growth_yoy": -0.07,
#     "analyst_sentiment": "bearish"
#   },
#   "executive_summary": "• Ingresos de 14.3B USD, caída del 7% interanual\n• Margen operativo negativo por cargos de reestructuración\n• Guidance del Q1 2027 por debajo de consenso\n• Plan de reducción de costes en curso con 15.000 empleados afectados\n• Deuda neta elevada, ratio Deuda/EBITDA superior a 4x",
#   "global_signal": "bearish",
#   "confidence_notes": "PER no calculable por beneficio negativo. Métricas extraídas del earnings release, no del 10-K completo."
# }
