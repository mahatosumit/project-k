"""Templating: one Jinja2 environment with i18n, INR formatting and CSRF available
to every template, so a page cannot accidentally render an unescaped or
mislabelled amount.

The locale resolution order is deliberate:
    ?lang=  ->  the vasool_lang cookie  ->  the organisation's saved locale  ->  English
That makes the header language switcher actually work without a login, while the
organisation's own setting remains the default for its staff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.domain.gst import STATE_CODES
from app.domain.money import format_paise, paise_to_decimal
from app.domain.msmed import stage_label
from app.i18n import FONT_STACKS, LOCALES, Translator, normalise_locale
from app.web.deps import CSRF_SESSION_KEY

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

LANG_COOKIE = "vasool_lang"

# Jinja autoescape is on for .html by default in Starlette's Jinja2Templates; the
# test suite asserts it rather than trusting the default silently.


def _money(paise: Any, symbol: bool = True) -> str:
    try:
        return format_paise(int(paise or 0), symbol=symbol)
    except (TypeError, ValueError):
        return ""


def _money_plain(paise: Any) -> str:
    try:
        return f"{paise_to_decimal(int(paise or 0)):,.2f}"
    except (TypeError, ValueError):
        return ""


def _date(value: Any, locale: str = "en") -> str:
    if value is None:
        return ""
    months_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    months_hi = ["जन", "फ़र", "मार्च", "अप्रैल", "मई", "जून", "जुल", "अग", "सित", "अक्ट", "नव", "दिस"]
    months = months_hi if locale == "hi" else months_en
    try:
        return f"{value.day:02d} {months[value.month - 1]} {value.year}"
    except (AttributeError, IndexError):
        return str(value)


def _datetime(value: Any) -> str:
    if value is None:
        return ""
    return value.strftime("%d %b %Y, %H:%M")


def resolve_locale(request: Request, org: Any = None) -> str:
    requested = request.query_params.get("lang")
    if requested:
        return normalise_locale(requested)
    cookie = request.cookies.get(LANG_COOKIE)
    if cookie:
        return normalise_locale(cookie)
    if org is not None:
        return normalise_locale(getattr(org, "locale", None))
    return normalise_locale(None)


def render(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    locale: str | None = None,
    user: Any = None,
    org: Any = None,
):
    settings = get_settings()
    chosen = normalise_locale(locale) if locale else resolve_locale(request, org)
    translator: Translator = Translator(chosen)

    ctx: dict[str, Any] = {
        "request": request,
        "t": translator,
        "locale": chosen,
        "locales": LOCALES,
        # Injected globally so a template can never crash because one route forgot
        # to pass a shared lookup.
        "states": STATE_CODES,
        "stage_label": lambda s: stage_label(s, chosen),
        "font_stack": FONT_STACKS.get(chosen, FONT_STACKS["en"]),
        "settings": settings,
        "app_name": settings.app_name,
        "csrf_token": request.session.get(CSRF_SESSION_KEY) if hasattr(request, "session") else "",
        "user": user,
        "org": org,
        "money": _money,
        "money_plain": _money_plain,
        "fmt_date": lambda v: _date(v, chosen),
        "fmt_datetime": _datetime,
        "asset_version": "1",
    }
    ctx.update(context or {})
    response = templates.TemplateResponse(
        request, template_name, ctx, status_code=status_code, headers={"Cache-Control": "no-store"}
    )

    # Persist an explicit language choice so it survives navigation.
    if request.query_params.get("lang"):
        response.set_cookie(
            LANG_COOKIE,
            chosen,
            max_age=60 * 60 * 24 * 365,
            httponly=False,  # a preference, not a secret; the client may read it
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
    return response
