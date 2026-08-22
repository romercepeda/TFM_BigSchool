"""Internal exchange code → EODHD exchange suffix lookup — Spec D12 §4.

EODHD identifies instruments as ``<SYMBOL>.<EXCHANGE_CODE>`` (e.g. ``SAN.MC``).
"Internal" here means whatever this codebase already stores on ``Asset.market``
— which is Twelve Data's own `exchange` field value (Spec D09 §3.1). EODHD's
suffix convention does not always match Twelve Data's, so this is the one
place that knows the translation (D12 §4).

Consumed by `market_data/symbols.py`'s `provider_symbol()`, which the cascade
layer (Changeset C04 §2) uses to build the per-provider qualified ticker.
The pre-cascade single-provider path in `market_data/service.py` has its own
separate `_US_EXCHANGES`/`_provider_symbol()` — intentionally not unified
with this module until Changeset C04 Step 7 removes that legacy path
entirely, so the live path is never touched mid-migration.

NOTE: all entries below have been verified live against Twelve Data's
symbol_search `exchange` field and EODHD's real-time endpoint (2026-07-17,
BMW/MBG/TEF/RNO/BP). Twelve Data reports Xetra-listed instruments as "XETR"
(not "XETRA" as this map originally assumed), which meant every Xetra asset
(e.g. BMW, Mercedes-Benz/MBG) raised "no EODHD exchange mapping" here and
fell through to Finnhub, which also refuses non-US symbols — the on-demand
current-price cascade was exhausted with no working provider. EODHD's own
suffix for Xetra is confirmed correct as "XETRA" (e.g. BMW.XETRA, MBG.XETRA
both return live quotes); only the internal *key* was wrong.
"""

from app.services.market_data.types import ProviderError

# US exchanges needing no market suffix internally — the single source of
# truth for both this module and market_data/symbols.py.
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "OTC", "CBOE", "NMFQS"}

_US_EODHD_SUFFIX = "US"

# Internal (Twelve Data) exchange code -> EODHD exchange code.
EXCHANGE_TO_EODHD: dict[str, str] = {
    "BME": "MC",  # Madrid — e.g. SAN.MC
    "XETR": "XETRA",  # Frankfurt/Xetra — e.g. BMW.XETRA, SAP.XETRA
    "EURONEXT": "PA",  # Euronext Paris — e.g. AIR.PA
    "LSE": "LSE",  # London — e.g. BP.LSE
}


def to_eodhd_exchange_code(internal_market: str | None) -> str:
    """Translate an internal exchange code to EODHD's suffix convention.

    `internal_market=None` is treated as a US exchange (no suffix needed
    internally, but EODHD still requires the explicit ".US" suffix).

    Raises ProviderError(error_kind="api_error") for an exchange this adapter
    has no mapping for, rather than guessing — per D12's "no silent
    fallback" principle.
    """
    if internal_market is None:
        return _US_EODHD_SUFFIX

    code = internal_market.strip().upper()
    if code in US_EXCHANGES:
        return _US_EODHD_SUFFIX
    if code in EXCHANGE_TO_EODHD:
        return EXCHANGE_TO_EODHD[code]

    raise ProviderError(
        error_kind="api_error",
        retryable=False,
        upstream_message=f"No EODHD exchange mapping for internal market code {internal_market!r}.",
    )
