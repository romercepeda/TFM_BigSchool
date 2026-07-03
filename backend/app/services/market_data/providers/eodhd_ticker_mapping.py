"""Internal exchange code → EODHD exchange suffix lookup — Spec D12 §4.

EODHD identifies instruments as ``<SYMBOL>.<EXCHANGE_CODE>`` (e.g. ``SAN.MC``).
"Internal" here means whatever this codebase already stores on ``Asset.market``
— which is Twelve Data's own `exchange` field value (Spec D09 §3.1), since that
is the provider `_provider_symbol()` (market_data/service.py) was written
against. EODHD's suffix convention does not always match Twelve Data's, so
this is the one place that knows the translation (D12 §4).

Not wired into the cascade yet — Changeset C04 §2 (the cascade layer) is
what will call `to_eodhd_exchange_code()` from `_provider_symbol()` once
"eodhd" becomes a selectable provider.

NOTE: the European entries below (XETRA, EURONEXT) are the author's best
knowledge of Twelve Data's exchange field values and have not been verified
against a live Twelve Data response — confirm before relying on them for a
real Xetra/Euronext asset. BME (Madrid) and LSE (London) are already used
elsewhere in this codebase (see market_data/service.py's TEF:BME example)
and are confirmed.
"""

from app.services.market_data.types import ProviderError

# US exchanges — mirrors market_data/service.py's _US_EXCHANGES. Duplicated
# rather than imported to avoid a providers/ → service.py dependency; both
# are static reference tables unlikely to drift independently.
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "OTC", "CBOE", "NMFQS"}

_US_EODHD_SUFFIX = "US"

# Internal (Twelve Data) exchange code -> EODHD exchange code.
EXCHANGE_TO_EODHD: dict[str, str] = {
    "BME": "MC",  # Madrid — e.g. SAN.MC
    "XETRA": "XETRA",  # Frankfurt/Xetra — e.g. SAP.XETRA
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
    if code in _US_EXCHANGES:
        return _US_EODHD_SUFFIX
    if code in EXCHANGE_TO_EODHD:
        return EXCHANGE_TO_EODHD[code]

    raise ProviderError(
        error_kind="api_error",
        retryable=False,
        upstream_message=f"No EODHD exchange mapping for internal market code {internal_market!r}.",
    )
