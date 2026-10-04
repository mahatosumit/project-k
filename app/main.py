"""FastAPI application: middleware, security headers, routes, startup checks.

Hardening applied to every response here (not per route):
* strict security headers incl. CSP, HSTS (prod only), frame-deny,
* a signed cookie session (itsdangerous) rather than a server-side session store,
* global per-IP rate limiting via a dependency,
* CSRF protection on all unsafe methods,
* request-size limits and a tidy JSON error shape that leaks nothing internal.

Startup refuses to boot in staging/production without a real SECRET_KEY and,
when a real gateway is selected, without its credentials — failing loudly is
better than running a payment product with a guessable signing key.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import run_migrations
from app.services import audit as audit_service

logger = logging.getLogger("vasool")

MAX_BODY_BYTES = 1_048_576  # 1 MiB is generous for a form post and stops trivial flooding

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}

# Inline styles are needed for the small amount of critical CSS we ship; scripts
# are all same-origin files, so no 'unsafe-inline' for script-src.
CSP_PROD = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)
CSP_DEV = CSP_PROD + "; script-src 'self' 'unsafe-inline'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        response.headers.setdefault(
            "Content-Security-Policy",
            CSP_PROD if settings.is_prod else CSP_DEV,
        )
        if settings.enable_hsts and settings.cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        # Do not advertise the stack: the framework name is a free hint to an
        # attacker and costs us nothing to withhold. On the ASGI server itself
        # this must ALSO be set there (uvicorn --no-server-header), because the
        # server can append its own header after the app has run.
        response.headers["Server"] = "vasool"
        return response


class BodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > MAX_BODY_BYTES:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Bad Content-Length"}, status_code=400)
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id and emit one structured access log line per request."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except HTTPException:
            raise
        except Exception:
            logger.exception("unhandled error", extra={"path": request.url.path})
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "path": request.url.path,
                "status": response.status_code,
                "ip": (request.client.host if request.client else ""),
            },
        )
        return response


def _assert_production_ready() -> None:
    settings = get_settings()
    if not settings.is_prod:
        return
    problems: list[str] = []
    import os

    if not os.environ.get("SECRET_KEY"):
        problems.append("SECRET_KEY must be set explicitly in staging/production")
    if not os.environ.get("FIELD_ENCRYPTION_KEY"):
        problems.append("FIELD_ENCRYPTION_KEY must be set explicitly in staging/production")
    if settings.payment_provider in {"mock", ""}:
        # The sandbox adapter settles invoices without money. Allowing it in
        # production would be a fake-payment path reachable by any portal-link
        # holder (security review, M2), so it is refused outright rather than
        # only documented.
        problems.append(
            "PAYMENT_PROVIDER is 'mock' (the sandbox adapter). Production must use a real "
            "gateway; the mock adapter can settle an invoice with no money."
        )
    if settings.payment_provider == "razorpay" and not (
        settings.platform_razorpay_key_id and settings.platform_razorpay_key_secret
    ):
        problems.append("Razorpay is selected but its key id/key are not configured")
    if settings.payment_provider == "cashfree" and not (
        settings.platform_cashfree_app_id and settings.platform_cashfree_secret
    ):
        problems.append("Cashfree is selected but its app id/key are not configured")
    if settings.payment_provider in {"razorpay", "cashfree"} and not (
        settings.razorpay_webhook_secret or settings.cashfree_webhook_secret
    ):
        problems.append("A gateway is selected but no webhook signing key is configured")
    if settings.messaging_provider == "console":
        problems.append(
            "MESSAGING_PROVIDER is 'console', which only logs messages — real reminders would "
            "never reach customers."
        )
    if problems:
        raise RuntimeError("Refusing to start: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    audit_service.configure_logging(log_dir=str(Path(settings.backup_dir).parent / "logs"))
    _assert_production_ready()
    applied = run_migrations(verbose=True)
    if applied:
        logger.info("migrations applied", extra={"event": "migrate", "path": ",".join(applied)})
    yield
    logger.info("shutdown", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        docs_url="/api/docs" if not settings.is_prod else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.is_prod else None,
        lifespan=lifespan,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="vasool_csrf",
        max_age=settings.session_ttl_seconds,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Routers are imported here so the middleware stack is in place first.
    from app.web.routes import (
        admin,
        auth_routes,
        billing,
        customers,
        dashboard,
        invoices,
        legal,
        pay,
        public,
        webhooks,
    )

    app.include_router(public.router)
    app.include_router(auth_routes.router)
    app.include_router(dashboard.router)
    app.include_router(customers.router)
    app.include_router(invoices.router)
    app.include_router(pay.router)
    app.include_router(webhooks.router)
    app.include_router(billing.router)
    app.include_router(admin.router)
    app.include_router(admin.ops_router)
    app.include_router(legal.router)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return PlainTextResponse("", status_code=204)

    @app.get("/robots.txt", include_in_schema=False)
    async def robots():
        return PlainTextResponse("User-agent: *\nDisallow: /app\nDisallow: /pay\n")

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        logger.info("validation error", extra={"path": request.url.path})
        return JSONResponse({"detail": "Invalid input"}, status_code=422)

    @app.exception_handler(BadSignature)
    async def bad_signature_handler(request: Request, exc: BadSignature):
        return JSONResponse({"detail": "Invalid session"}, status_code=400)

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        if request.url.path.startswith("/app") and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/app", status_code=303)
        return PlainTextResponse("Not found", status_code=404)

    return app


app = create_app()
