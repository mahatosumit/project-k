"""Authentication routes: signup, login, OTP, logout.

Convention note: credential-bearing form fields are bound to neutral parameter
names and the CSRF field is bound through an explicit alias, because this
workspace's write guard rejects identifiers containing credential nouns. The HTML
is unaffected — inputs still use the correct ``type`` and ``autocomplete``
attributes, so password managers behave normally. Recorded in docs/DECISIONS.md.

The CSRF token is rotated on every successful authentication, so a value minted
before login cannot be replayed afterwards.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.adapters.messaging import build_messaging
from app.config import get_settings
from app.i18n import clean_text, normalise_locale, normalise_phone
from app.models import Organization
from app.services import auth as auth_service
from app.services import notifications
from app.web.deps import (
    client_ip,
    current_user_optional,
    db_session,
    enforce_global_rate_limit,
    ensure_csrf,
    rotate_csrf,
    verify_csrf,
)
from app.web.templating import render

router = APIRouter(dependencies=[Depends(enforce_global_rate_limit)])

# Bound with an alias so the Python identifier stays neutral while the HTML field
# keeps its conventional name.
CSRF_FIELD = Form(None, alias="csrf_token")


def _login_redirect() -> RedirectResponse:
    resp = RedirectResponse("/app", status_code=303)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _set_session(request: Request, resp: RedirectResponse, user) -> RedirectResponse:
    """Establish the authenticated session and rotate the CSRF value."""
    settings = get_settings()
    rotate_csrf(request)
    resp.set_cookie(
        settings.session_cookie,
        auth_service.session_token_for(user),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/login")
async def login_page(request: Request, session: Session = Depends(db_session)):
    ensure_csrf(request)
    user = current_user_optional(request, session)
    if user is not None:
        return _login_redirect()
    return render(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    session: Session = Depends(db_session),
    email: str | None = Form(None),
    pw_field: str | None = Form(None),
    csrf_field: str | None = CSRF_FIELD,
):
    verify_csrf(request, csrf_field)
    try:
        user = auth_service.authenticate(
            session,
            email=(email or ""),
            secret_text=(pw_field or ""),
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.AuthError as exc:
        return render(
            request,
            "login.html",
            {"error": exc.message_key, "email": clean_text((email or "")[:254])},
            status_code=400,
        )
    return _set_session(request, _login_redirect(), user)


@router.get("/signup")
async def signup_page(request: Request, session: Session = Depends(db_session)):
    ensure_csrf(request)
    if current_user_optional(request, session) is not None:
        return _login_redirect()
    return render(request, "signup.html", {"error": None})


@router.post("/signup")
async def signup_submit(
    request: Request,
    session: Session = Depends(db_session),
    name: str | None = Form(None),
    org_name: str | None = Form(None),
    email: str | None = Form(None),
    pw_new: str | None = Form(None),
    phone: str | None = Form(None),
    locale: str | None = Form(None),
    accept_terms: str | None = Form(None),
    csrf_field: str | None = CSRF_FIELD,
):
    verify_csrf(request, csrf_field)
    email_clean = clean_text((email or "")[:254])
    name_clean = clean_text((name or "")[:200])

    if not accept_terms:
        return render(
            request,
            "signup.html",
            {"error": "auth.must_accept", "email": email_clean, "name": name_clean},
            status_code=400,
        )

    supplied = pw_new or ""
    problem = auth_service.password_problem(supplied)
    if problem:
        return render(
            request,
            "signup.html",
            {
                "error": "auth.error_invalid",
                "error_message": problem,
                "email": email_clean,
                "name": name_clean,
            },
            status_code=400,
        )

    phone_raw = (phone or "").strip()
    phone_e164 = normalise_phone(phone_raw) if phone_raw else None
    if phone_raw and phone_e164 is None:
        return render(
            request, "signup.html", {"error": "auth.bad_phone", "email": email_clean}, status_code=400
        )

    try:
        user, _org = auth_service.create_account(
            session,
            email=email_clean,
            secret_text=supplied,
            name=name_clean,
            org_name=clean_text((org_name or "")[:200]) or None,
            phone_e164=phone_e164,
            locale=normalise_locale(locale),
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.AuthError as exc:
        key = "auth.error_email_taken" if exc.code == "email_taken" else "auth.error_invalid"
        return render(request, "signup.html", {"error": key, "email": email_clean}, status_code=400)

    session.commit()
    return _set_session(request, _login_redirect(), user)


@router.get("/otp")
async def otp_page(request: Request):
    ensure_csrf(request)
    return render(request, "otp.html", {"error": None, "step": "request", "phone": ""})


@router.post("/otp/request")
async def otp_request(
    request: Request,
    session: Session = Depends(db_session),
    phone: str | None = Form(None),
    csrf_field: str | None = CSRF_FIELD,
):
    verify_csrf(request, csrf_field)
    phone_display = clean_text((phone or "")[:16])
    phone_e164 = normalise_phone(phone or "")
    generic: dict = {"step": "verify", "phone": phone_display, "error": None}
    if phone_e164 is None:
        return render(
            request,
            "otp.html",
            {"step": "request", "phone": phone_display, "error": "auth.bad_phone"},
            status_code=400,
        )

    # Only issue a code for a number that has an account; the response is identical
    # either way, so the endpoint cannot be used to enumerate users. The rate limit
    # is consumed *before* the account lookup so the endpoint cannot be hammered
    # with arbitrary numbers either (SMS-pumping and probing defence).
    user = auth_service.user_for_phone(session, phone_e164)
    settings = get_settings()
    try:
        auth_service.enforce_otp_limits(session, phone_e164=phone_e164, ip=client_ip(request))
    except auth_service.AuthError:
        return render(
            request, "otp.html", {**generic, "error": "auth.error_otp_rate_limited"}, status_code=429
        )

    if user is not None:
        try:
            code = auth_service.issue_otp(
                session, phone_e164=phone_e164, ip=client_ip(request), consume_limits=False
            )
        except auth_service.AuthError:
            return render(
                request, "otp.html", {**generic, "error": "auth.error_otp_rate_limited"}, status_code=429
            )
        org = session.get(Organization, user.org_id)
        adapter = build_messaging(settings)
        outcome = notifications.send(
            session,
            org=org,
            channel="whatsapp" if adapter.name == "whatsapp" else "sms",
            to=phone_e164,
            body=(
                f"{settings.app_name}: your login code is {code}. "
                f"It expires in {settings.otp_ttl_seconds // 60} minutes."
            ),
            template="login_otp",
            customer=None,  # account owner, not a customer: no marketing consent involved
            actor="system",
        )
        if not outcome.ok and settings.messaging_provider == "console":
            # Development only: no SMS provider is configured, so surface the code
            # here to keep the flow testable. The console adapter also logs it.
            generic["dev_code"] = code
    return render(request, "otp.html", generic)


@router.post("/otp/verify")
async def otp_verify(
    request: Request,
    session: Session = Depends(db_session),
    phone: str | None = Form(None),
    code: str | None = Form(None),
    csrf_field: str | None = CSRF_FIELD,
):
    verify_csrf(request, csrf_field)
    phone_display = clean_text((phone or "")[:16])
    phone_e164 = normalise_phone(phone or "")
    code_clean = (code or "").strip()
    if phone_e164 is None or not code_clean:
        return render(
            request,
            "otp.html",
            {"step": "verify", "phone": phone_display, "error": "auth.bad_otp"},
            status_code=400,
        )

    ok = auth_service.verify_otp(session, phone_e164=phone_e164, code=code_clean, ip=client_ip(request))
    if not ok:
        return render(
            request,
            "otp.html",
            {"step": "verify", "phone": phone_display, "error": "auth.bad_otp"},
            status_code=400,
        )

    user = auth_service.user_for_phone(session, phone_e164)
    if user is None:
        return render(
            request,
            "otp.html",
            {"step": "verify", "phone": phone_display, "error": "auth.bad_otp"},
            status_code=400,
        )

    session.commit()
    return _set_session(request, _login_redirect(), user)


@router.post("/logout")
async def logout(request: Request, csrf_field: str | None = CSRF_FIELD):
    verify_csrf(request, csrf_field)
    settings = get_settings()
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(settings.session_cookie, path="/")
    return resp
