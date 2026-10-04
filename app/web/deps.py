"""Shared FastAPI dependencies: DB session, current user, CSRF, rate limiting.

Security-relevant behaviour lives here so every route gets it by default:
* global per-IP rate limiting (a route cannot forget it),
* CSRF tokens for every state-changing request, rotated on session change,
* security headers set on every response in ``app.main``.
"""

from __future__ import annotations

import datetime as dt
import hmac
import secrets
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Customer, Organization, User
from app.security import new_csrf_token
from app.services import auth as auth_service
from app.services import ratelimit

CSRF_SESSION_KEY = "csrf_token"


def client_ip(request: Request) -> str:
    """Best-effort client IP.

    We deliberately do NOT trust ``X-Forwarded-For`` unless a proxy is declared,
    because a spoofed header would defeat rate limiting. Behind a real proxy,
    uvicorn is configured with ``--proxy-headers`` and only then is the header
    meaningful.
    """
    if request.client and request.client.host:
        return request.client.host[:45]
    return "unknown"


def get_settings_dep() -> Settings:
    return get_settings()


def db_session() -> Iterator[Session]:
    yield from get_db()


def _session_token(request: Request) -> str | None:
    settings = get_settings()
    return request.cookies.get(settings.session_cookie)


def current_user_optional(
    request: Request,
    session: Session = Depends(db_session),
) -> User | None:
    token = _session_token(request)
    return auth_service.resolve_session(session, token)


def current_user(
    request: Request,
    session: Session = Depends(db_session),
) -> User:
    user = current_user_optional(request, session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def current_org(
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
) -> Organization:
    org = session.get(Organization, user.org_id)
    if org is None:  # pragma: no cover - referential integrity makes this unreachable
        raise HTTPException(status_code=404, detail="organisation not found")
    return org


def ensure_csrf(request: Request) -> str:
    """Return the CSRF token for this session, creating one if needed."""
    token = request.session.get(CSRF_SESSION_KEY) if hasattr(request, "session") else None
    if not token:
        token = new_csrf_token()
        if hasattr(request, "session"):
            request.session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf(request: Request) -> str:
    """Issue a fresh CSRF token. Called whenever the authenticated principal
    changes (login, signup, OTP login) so a token minted before authentication
    cannot be replayed afterwards."""
    token = new_csrf_token()
    if hasattr(request, "session"):
        request.session[CSRF_SESSION_KEY] = token
    return token


def verify_csrf(request: Request, provided: str | None) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = request.session.get(CSRF_SESSION_KEY) if hasattr(request, "session") else None
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")


def enforce_global_rate_limit(request: Request, session: Session = Depends(db_session)) -> None:
    settings = get_settings()
    path = request.url.path
    # Never rate-limit static assets or health checks.
    if path.startswith("/static") or path in {"/healthz", "/readyz", "/favicon.ico", "/robots.txt"}:
        return
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        limit = settings.global_rate_limit_per_minute * 3
    else:
        limit = settings.global_rate_limit_per_minute
    verdict = ratelimit.hit(
        session,
        bucket="global_ip",
        key=client_ip(request),
        limit=limit,
        window_seconds=60,
    )
    if not verdict.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(verdict.retry_after_seconds)},
        )


def owned_customer(session: Session, org: Organization, customer_id: str) -> Customer:
    """Authorisation helper: a customer must belong to the caller's org.

    Every customer/invoice lookup goes through a helper like this — the
    authorisation check is not left to each route author's memory.
    """
    customer = session.get(Customer, customer_id)
    if customer is None or customer.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    return customer


def new_nonce() -> str:
    return secrets.token_urlsafe(16)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)
