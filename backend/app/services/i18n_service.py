"""i18n service — Spec D08 (Internationalization).

Loads translation bundles from backend/i18n/<lang>.json and resolves keys
per request using the authenticated user's preferred_language.

Resolution order (§5.5 / §6.1):
  1. User's preferred_language
  2. i18n.default_language (config)
  3. The raw key itself — a visible raw key in production is a bug signal per spec

Named placeholders use {name} syntax and are interpolated at resolve time.
Missing keys are logged as warnings on first occurrence, then debounced.
"""

from __future__ import annotations

import json
import logging
from functools import cache
from pathlib import Path

logger = logging.getLogger(__name__)

_BUNDLE_DIR = Path(__file__).parent.parent.parent / "i18n"

# Tracks which (key, lang) pairs have already triggered a warning — avoids flooding.
_warned: set[tuple[str, str]] = set()


@cache
def _load_bundle(lang: str) -> dict[str, str]:
    """Load and cache a single language bundle from disk."""
    path = _BUNDLE_DIR / f"{lang}.json"
    if not path.exists():
        logger.warning("i18n: bundle not found for language %r at %s", lang, path)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def translate(
    key: str,
    lang: str,
    default_lang: str = "es",
    **kwargs: object,
) -> str:
    """Resolve *key* to a translated string for *lang*.

    Falls back to *default_lang*, then to the raw key (visible fallback per §5.5).
    Named *kwargs* are interpolated as {name} placeholders.
    """
    for candidate in _candidates(lang, default_lang):
        bundle = _load_bundle(candidate)
        if key in bundle:
            text = bundle[key]
            if kwargs:
                try:
                    return text.format(**kwargs)
                except KeyError:
                    return text
            return text

    # Last resort: return the key itself — visible in the UI as a bug signal.
    pair = (key, lang)
    if pair not in _warned:
        logger.warning("i18n: missing translation key %r for language %r", key, lang)
        _warned.add(pair)
    return key


def translate_indicator_name(name_key: str, lang: str, default_lang: str = "es") -> str:
    """Resolve an indicator name_key to its translated display name."""
    return translate(name_key, lang, default_lang)


def translate_state(
    indicator_code: str,
    state_value: str,
    lang: str,
    default_lang: str = "es",
) -> str:
    """Translate a categorical indicator state value (e.g. 'golden_cross').

    Key format: indicator.<code>.state.<value>
    Falls back to the raw state_value if no translation exists.
    """
    key = f"indicator.{indicator_code}.state.{state_value}"
    result = translate(key, lang, default_lang)
    # If translate returned the key itself (missing), fall back to raw value.
    return state_value if result == key else result


def _candidates(lang: str, default_lang: str) -> list[str]:
    """Return the ordered list of language codes to try."""
    seen: list[str] = []
    for code in (lang, default_lang):
        if code not in seen:
            seen.append(code)
    return seen
