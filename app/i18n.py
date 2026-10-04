"""Minimal i18n: locale string tables loaded from JSON data files.

The translatable copy lives in ``app/locales/<locale>.json`` as data — the normal
way to ship UI strings, and it keeps the Python module purely logic. Adding
Marathi or Tamil is a new JSON file plus an entry in ``LOCALES``: no code change,
and the same mechanism covers web pages, reminder messages and invoices.

Mixed-script input is handled by the sanitising helpers: Hindi, Hinglish and
English text all pass through unchanged, but control characters and unbalanced
markup are stripped.
"""

from __future__ import annotations

import contextlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LOCALE = "en"
LOCALES: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
}
LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Locale -> font stack. Noto covers Devanagari; kept in one place so a new
# script only needs a font added here.
FONT_STACKS: dict[str, str] = {
    "en": "'Noto Sans','Segoe UI',system-ui,sans-serif",
    "hi": "'Noto Sans Devanagari','Noto Sans','Nirmala UI',system-ui,sans-serif",
}


@lru_cache(maxsize=8)
def _load_table(locale: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if not str(k).startswith("_")}


class Translator:
    """Look up a key in a locale, falling back to English then to the key."""

    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        self.locale = locale if locale in LOCALES else DEFAULT_LOCALE
        self._table = _load_table(self.locale)
        self._fallback = _load_table(DEFAULT_LOCALE) if self.locale != DEFAULT_LOCALE else self._table

    def __call__(self, key: str, **kwargs: Any) -> str:
        text = self._table.get(key) or self._fallback.get(key) or key
        if kwargs:
            # A missing placeholder must never break a page or a send.
            with contextlib.suppress(KeyError, IndexError):
                text = text.format(**kwargs)
        return text

    def has(self, key: str) -> bool:
        return key in self._table


def translator_for(locale: str | None) -> Translator:
    return Translator(locale or DEFAULT_LOCALE)


def normalise_locale(value: str | None) -> str:
    if not value:
        return DEFAULT_LOCALE
    candidate = value.strip().lower()[:2]
    return candidate if candidate in LOCALES else DEFAULT_LOCALE


def available_locales() -> dict[str, str]:
    return dict(LOCALES)


# --- Input hygiene ---------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RUN = re.compile(r"[ \t\u00a0]{2,}")
_TAG_LIKE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]{0,200}>")


def clean_text(value: str | None, *, max_length: int = 2000, allow_newlines: bool = True) -> str:
    """Sanitise free text from any locale.

    Preserves Devanagari, Arabic-Indic digits and emoji; strips control
    characters, collapses runs of spaces, and defuses obvious markup so the value
    is safe to show. Templates still escape on output — this is defence in depth,
    not a replacement for escaping.
    """
    if value is None:
        return ""
    text = str(value)
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TAG_LIKE.sub("", text)
    text = _WHITESPACE_RUN.sub(" ", text)
    if not allow_newlines:
        text = text.replace("\n", " ")
    text = text.strip()
    return text[:max_length]


def clean_multiline(value: str | None, *, max_length: int = 5000) -> str:
    return clean_text(value, max_length=max_length, allow_newlines=True)


def normalise_phone(value: str | None, *, default_country: str = "91") -> str | None:
    """Normalise an Indian mobile number to E.164 (+91XXXXXXXXXX).

    Accepts '98765 43210', '+91-98765-43210', '0091 9876543210'. Returns None
    when the result is not a plausible Indian mobile number, so the caller can
    surface a validation error instead of silently storing junk.
    """
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return f"+{default_country}{digits}"
    if len(digits) == 12 and digits.startswith(default_country) and digits[2] in "6789":
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        return f"+{default_country}{digits[1:]}"
    if len(digits) == 13 and digits.startswith("0" + default_country):
        return f"+{digits[1:]}"
    return None


def digits_only(value: str | None, *, max_length: int = 6) -> str:
    return re.sub(r"\D", "", str(value or ""))[:max_length]
