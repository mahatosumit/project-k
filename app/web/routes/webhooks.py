"""Webhook intake for payment gateways.

Two routes, one per provider, so the signing key used to verify a callback is
unambiguous. Both are:

* rate limited per IP (a webhook endpoint is a public, unauthenticated surface),
* verified by HMAC over the raw body before anything is parsed,
* idempotent — a duplicate delivery returns 200 without re-applying the payment.

We always return 2xx once the event has been *received* even if it could not be
applied, because a non-2xx makes the gateway retry forever with no new
information; unapplied events are surfaced through the reconciliation job and
the audit log instead.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import payments as payment_service
from app.services import ratelimit
from app.web.deps import client_ip, db_session

logger = logging.getLogger("vasool.webhooks")

router = APIRouter(prefix="/webhooks")

WEBHOOK_IP_LIMIT = 600  # per hour, per IP


def _limited(session: Session, ip: str, provider: str) -> bool:
    verdict = ratelimit.hit(
        session,
        bucket=f"webhook_{provider}",
        key=ip,
        limit=WEBHOOK_IP_LIMIT,
        window_seconds=3600,
    )
    return not verdict.allowed


async def _handle(request: Request, session: Session, provider: str, headers: dict[str, str]) -> JSONResponse:
    ip = client_ip(request)
    if _limited(session, ip, provider):
        return JSONResponse({"status": "rate_limited"}, status_code=429)

    raw = await request.body()
    if not raw:
        return JSONResponse({"status": "ignored", "reason": "empty body"}, status_code=200)
    if len(raw) > 262_144:
        return JSONResponse({"status": "ignored", "reason": "body too large"}, status_code=200)

    settings = get_settings()
    try:
        outcome = payment_service.process_webhook(
            session,
            provider=provider,
            headers=headers,
            raw_body=raw,
            org=None,  # resolved from the order inside the handler
            settings=settings,
            ip=ip,
        )
    except Exception:
        logger.exception("webhook processing error", extra={"path": request.url.path})
        session.rollback()
        return JSONResponse({"status": "error"}, status_code=200)

    if outcome.accepted:
        session.commit()
    else:
        session.commit()

    logger.info(
        "webhook",
        extra={"path": request.url.path, "status": outcome.status, "ip": ip},
    )
    # Always 2xx for a delivery we have *received*, including one we refuse. A
    # non-2xx makes the gateway retry forever with no new information, and the
    # refusal is already recorded in payment_events and the audit trail. The rate
    # limit above bounds the volume an attacker can generate.
    return JSONResponse(
        {
            "status": outcome.status,
            "duplicate": outcome.duplicate,
            "detail": outcome.detail,
        },
        status_code=200,
    )


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    session: Session = Depends(db_session),
    x_razorpay_signature: str = Header(default=""),
    x_razorpay_event_id: str = Header(default=""),
):
    headers = {
        "X-Razorpay-Signature": x_razorpay_signature,
        "x-razorpay-event-id": x_razorpay_event_id,
        "content-type": request.headers.get("content-type", ""),
    }
    return await _handle(request, session, "razorpay", headers)


@router.post("/cashfree")
async def cashfree_webhook(
    request: Request,
    session: Session = Depends(db_session),
    x_webhook_signature: str = Header(default=""),
    x_webhook_timestamp: str = Header(default=""),
    x_idempotency_header: str = Header(default=""),
):
    headers = {
        "x-webhook-signature": x_webhook_signature,
        "x-webhook-timestamp": x_webhook_timestamp,
        "x-idempotency-header": x_idempotency_header,
        "content-type": request.headers.get("content-type", ""),
    }
    return await _handle(request, session, "cashfree", headers)


@router.post("/mock")
async def mock_webhook(
    request: Request,
    session: Session = Depends(db_session),
    x_razorpay_signature: str = Header(default=""),
):
    """Sandbox adapter's callback target. Refuses to run when a real gateway is
    configured, so it can never be used to fake a payment in production."""
    settings = get_settings()
    if settings.payment_provider not in {"mock", ""}:
        return JSONResponse({"status": "rejected", "reason": "not enabled"}, status_code=404)
    if settings.is_prod:
        return JSONResponse({"status": "rejected", "reason": "not enabled"}, status_code=404)
    return await _handle(request, session, "mock", {"X-Razorpay-Signature": x_razorpay_signature})
