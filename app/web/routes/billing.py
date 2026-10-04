"""Billing routes: the merchant's own subscription to this product.

Design decision (see docs/DECISIONS.md): rather than betting the business on
RBI e-mandate recurring, which needs AFA on the first charge, a >=24h pre-debit
notice and only reliably supports small-ticket recurring, we sell **prepaid
periods** the merchant pays for explicitly. That is reliable for a solo
bootstrapper, needs no mandate infrastructure, and the renewal is a payment link
plus reminders rather than an invisible autocharge.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.payments import PaymentError
from app.config import get_settings
from app.models import GatewayOrder, Organization, Subscription, User
from app.models import utcnow as model_utcnow
from app.services import audit as audit_service
from app.services import payments as payment_service
from app.web.deps import (
    client_ip,
    current_org,
    current_user,
    db_session,
    enforce_global_rate_limit,
    ensure_csrf,
    verify_csrf,
)
from app.web.templating import render

router = APIRouter(prefix="/billing", dependencies=[Depends(enforce_global_rate_limit)])

# INR price points, set against what Indian businesses already pay for adjacent
# tools (myBillBook ~Rs 399/yr, Tally ~Rs 750/mo, Vyapar desktop ~Rs 3,099-3,399/yr).
PLANS: dict[str, dict[str, int | str]] = {
    "starter_monthly": {"code": "starter_monthly", "price_paise": 29900, "cycle": "monthly", "label": "Starter · monthly"},
    "starter_annual": {"code": "starter_annual", "price_paise": 299900, "cycle": "annual", "label": "Starter · annual (2 months free)"},
    "growth_annual": {"code": "growth_annual", "price_paise": 599900, "cycle": "annual", "label": "Growth · annual"},
}
TRIAL_DAYS = 14


@router.get("")
async def billing_page(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    subscription = session.scalar(
        select(Subscription).where(Subscription.org_id == org.id).order_by(Subscription.created_at.desc())
    )
    orders = session.scalars(
        select(GatewayOrder)
        .where(GatewayOrder.org_id == org.id, GatewayOrder.purpose == "subscription")
        .order_by(GatewayOrder.created_at.desc())
        .limit(20)
    ).all()
    settings = get_settings()
    return render(
        request,
        "billing.html",
        {
            "plans": PLANS,
            "subscription": subscription,
            "orders": orders,
            "trial_days": TRIAL_DAYS,
            "payment_mode": settings.payment_mode,
            "provider": settings.payment_provider,
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/subscribe")
async def subscribe(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    plan: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    chosen = PLANS.get(plan)
    if chosen is None:
        return RedirectResponse("/billing?error=plan", status_code=303)

    settings = get_settings()
    now = model_utcnow()

    subscription = session.scalar(select(Subscription).where(Subscription.org_id == org.id))
    if subscription is None:
        subscription = Subscription(
            org_id=org.id,
            plan_code=str(chosen["code"]),
            price_paise=int(chosen["price_paise"]),
            billing_cycle=str(chosen["cycle"]),
            status="trialing",
            started_at=now,
            current_period_end=now + dt.timedelta(days=TRIAL_DAYS),
        )
        session.add(subscription)
    else:
        subscription.plan_code = str(chosen["code"])
        subscription.price_paise = int(chosen["price_paise"])
        subscription.billing_cycle = str(chosen["cycle"])
        subscription.updated_at = now
    session.flush()

    try:
        adapter = payment_service.get_adapter(None, settings)
        result = adapter.create_order(
            __import__("app.adapters.payments", fromlist=["OrderRequest"]).OrderRequest(
                amount_paise=int(chosen["price_paise"]),
                receipt=f"sub-{org.id[:8]}-{int(now.timestamp())}",
                notes={"org_id": org.id, "purpose": "subscription", "return_url": f"{settings.base_url}/billing"},
                customer_id=org.id,
                customer_name=org.name,
                customer_email=org.billing_email or user.email,
                return_url=f"{settings.base_url}/billing/callback",
            )
        )
    except PaymentError:
        session.rollback()
        return RedirectResponse("/billing?error=gateway", status_code=303)

    order = GatewayOrder(
        org_id=org.id,
        subscription_id=subscription.id,
        purpose="subscription",
        provider=(result.provider_order_id and adapter.name) or adapter.name,
        mode=settings.payment_mode,
        provider_order_id=result.provider_order_id,
        amount_paise=result.amount_paise,
        status=result.status,
        notes=f'{{"org_id": "{org.id}"}}',
    )
    session.add(order)
    session.flush()
    audit_service.record(
        session,
        action="billing.subscribe_started",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="subscription",
        entity_id=subscription.id,
        ip=client_ip(request),
        detail={"plan": chosen["code"], "amount_paise": int(chosen["price_paise"]), "provider": adapter.name},
    )
    session.commit()

    if adapter.name == "mock":
        return RedirectResponse(f"/billing/sandbox/{order.provider_order_id}", status_code=303)
    return render(
        request,
        "checkout_redirect.html",
        {
            "checkout": result.checkout,
            "order_id": result.provider_order_id,
            "return_url": f"{settings.base_url}/billing/callback",
            "org": org,
            "user": user,
            "invoice": None,
            "customer": None,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.get("/sandbox/{order_id}")
async def sandbox_billing(
    order_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    settings = get_settings()
    if settings.is_prod or settings.payment_provider not in {"mock", ""}:
        return RedirectResponse("/billing", status_code=303)
    order = session.scalar(
        select(GatewayOrder).where(GatewayOrder.provider_order_id == order_id, GatewayOrder.org_id == org.id)
    )
    if order is None:
        return RedirectResponse("/billing", status_code=303)
    return render(
        request,
        "billing_sandbox.html",
        {"order": order, "org": org, "user": user},
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/sandbox/{order_id}/complete")
async def sandbox_billing_complete(
    order_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    outcome: str = Form("success"),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    settings = get_settings()
    if settings.is_prod or settings.payment_provider not in {"mock", ""}:
        return RedirectResponse("/billing", status_code=303)

    # Scope the order to the caller's own organisation BEFORE completing it. The
    # GET sibling already did this; without the check here, a user in one org
    # could settle another org's order by posting its id (security review, M3).
    owned = session.scalar(
        select(GatewayOrder).where(
            GatewayOrder.provider_order_id == order_id, GatewayOrder.org_id == org.id
        )
    )
    if owned is None:
        return RedirectResponse("/billing", status_code=303)

    from app.adapters.payments import MockAdapter

    adapter = payment_service.get_adapter(org, settings)
    if not isinstance(adapter, MockAdapter):
        return RedirectResponse("/billing", status_code=303)

    body, headers = adapter.build_webhook(
        order_id=order_id, event_key=f"sub_{order_id}_{outcome}", failed=(outcome != "success")
    )
    if outcome == "success":
        adapter.mark_paid(order_id)
    payment_service.process_webhook(
        session, provider=adapter.name, headers=headers, raw_body=body, org=org, settings=settings, ip=client_ip(request)
    )
    session.commit()
    return RedirectResponse("/billing/callback", status_code=303)


@router.get("/callback")
async def billing_callback(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    settings = get_settings()
    payment_service.reconcile_pending(session, min_age_minutes=0, limit=5, settings=settings)
    session.commit()
    subscription = session.scalar(
        select(Subscription).where(Subscription.org_id == org.id).order_by(Subscription.created_at.desc())
    )
    return render(
        request,
        "billing_callback.html",
        {"subscription": subscription, "org": org, "user": user},
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/cancel")
async def cancel_subscription(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    csrf_token: str = Form(""),
):
    """Cancel at period end. No dark patterns: one click, effective immediately
    for future renewals, and the paid-for period is never taken away."""
    verify_csrf(request, csrf_token)
    subscription = session.scalar(
        select(Subscription).where(Subscription.org_id == org.id).order_by(Subscription.created_at.desc())
    )
    if subscription is not None:
        subscription.cancel_at_period_end = True
        subscription.cancelled_at = model_utcnow()
        subscription.updated_at = model_utcnow()
        session.flush()
        audit_service.record(
            session,
            action="billing.cancelled",
            org_id=org.id,
            actor_type="user",
            actor_id=user.id,
            entity_type="subscription",
            entity_id=subscription.id,
            ip=client_ip(request),
        )
    session.commit()
    return RedirectResponse("/billing", status_code=303)


@router.post("/refund-request")
async def refund_request(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    reason: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    from app.i18n import clean_text
    from app.models import SupportRequest

    row = SupportRequest(
        org_id=org.id,
        subject_type="org",
        subject_id=org.id,
        channel="app",
        category="billing",
        message=clean_text(reason, max_length=2000) or "Refund requested (no reason given).",
        contact=user.email,
        sla_due_at=model_utcnow() + dt.timedelta(hours=48),
    )
    session.add(row)
    session.flush()
    audit_service.record(
        session,
        action="billing.refund_requested",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="support_request",
        entity_id=row.id,
        ip=client_ip(request),
    )
    session.commit()
    return RedirectResponse("/billing?ok=refund_requested", status_code=303)
