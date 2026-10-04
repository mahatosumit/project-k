"""Customer-facing payment portal.

Accessed by the customer from a WhatsApp/SMS link, authorised by an unguessable
per-customer link_key in the URL plus a per-invoice public link_key — never by a
guessable invoice number. A customer can:

* see the invoice and the amount due,
* pay via the merchant's gateway (hosted checkout — we never see card data),
* ask for a part-payment plan,
* say they have already paid (with a UTR) — this pauses the ladder,
* dispute the invoice — this also pauses the ladder.

Every action here is rate limited and audited, and none of them can change the
invoice total: a customer-reported payment is recorded as a *claim* for the
merchant to confirm.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.adapters.payments import PaymentError
from app.config import get_settings
from app.domain import ledger
from app.domain.gst import state_name
from app.domain.money import amount_in_words, format_paise, today_ist
from app.i18n import clean_text
from app.models import Customer, Dispute, Installment, InstallmentPlan, Invoice, Organization, SupportRequest
from app.models import utcnow as model_utcnow
from app.services import audit as audit_service
from app.services import notifications
from app.services import payments as payment_service
from app.services import portal as portal_service
from app.services import reminders as reminder_service
from app.web.deps import client_ip, db_session, enforce_global_rate_limit, ensure_csrf, verify_csrf
from app.web.templating import render

router = APIRouter(prefix="/pay", dependencies=[Depends(enforce_global_rate_limit)])

COMPLAINT_WINDOW_HOURS = 48


def _load(session: Session, invoice_id: str, link_key: str) -> tuple[Invoice, Customer, Organization]:
    """Authorise a portal request: invoice + matching public link_key, else 404."""
    if not link_key or len(link_key) < 16:
        raise HTTPException(status_code=404, detail="not found")
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="not found")
    customer = session.get(Customer, invoice.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="not found")
    # The link_key is per-invoice: derived from the customer link_key and invoice id so
    # it cannot be reused across invoices, and compared in a tokenised form.
    import hmac

    expected = _public_token(customer.portal_link_key, invoice.id)
    if not hmac.compare_digest(expected, link_key):
        raise HTTPException(status_code=404, detail="not found")
    org = session.get(Organization, invoice.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="not found")
    return invoice, customer, org


def _public_token(portal_link_key: str, invoice_id: str) -> str:
    """Retained name for callers that already import it; delegates to the service."""
    return portal_service.public_token(portal_link_key, invoice_id)


def portal_path(invoice: Invoice, customer: Customer) -> str:
    return portal_service.portal_path(invoice, customer)


@router.get("/{invoice_id}/{link_key}")
async def portal(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
):
    ensure_csrf(request)
    invoice, customer, org = _load(session, invoice_id, link_key)
    outstanding = ledger.outstanding_of(invoice)
    today = today_ist()
    open_dispute = None
    from sqlalchemy import select

    open_dispute = session.scalar(
        select(Dispute).where(Dispute.invoice_id == invoice.id, Dispute.status == "open").order_by(Dispute.created_at.desc())
    )
    plan = session.scalar(
        select(InstallmentPlan).where(InstallmentPlan.invoice_id == invoice.id, InstallmentPlan.status == "active")
    )
    installments = (
        session.scalars(select(Installment).where(Installment.plan_id == plan.id).order_by(Installment.seq)).all()
        if plan
        else []
    )
    return render(
        request,
        "pay.html",
        {
            "invoice": invoice,
            "customer": customer,
            "org": org,
            "outstanding_paise": outstanding,
            "days_overdue": max(0, (today - invoice.due_date).days),
            "words": amount_in_words(int(invoice.total_paise or 0)),
            "pos_name": state_name(invoice.place_of_supply_state_code),
            "link_key": link_key,
            "dispute": open_dispute,
            "plan": plan,
            "installments": installments,
            "gateway_connected": bool(org.gateway_provider),
            "error": request.query_params.get("error"),
        },
        locale=org.locale,
        org=org,
    )


@router.post("/{invoice_id}/{link_key}/start-payment")
async def start_payment(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice, customer, org = _load(session, invoice_id, link_key)
    if ledger.outstanding_of(invoice) <= 0:
        return RedirectResponse(f"/pay/{invoice_id}/{link_key}", status_code=303)

    settings = get_settings()
    return_url = f"{settings.base_url}/pay/{invoice_id}/{link_key}/callback"
    try:
        order, checkout = payment_service.create_invoice_payment_order(
            session,
            org=org,
            invoice=invoice,
            customer=customer,
            return_url=return_url,
            idempotency_key=f"inv-{invoice.id}-{int(model_utcnow().timestamp())}",
        )
    except PaymentError:
        session.rollback()
        return RedirectResponse(f"/pay/{invoice_id}/{link_key}?error=gateway", status_code=303)

    audit_service.record(
        session,
        action="portal.payment_started",
        org_id=org.id,
        actor_type="customer",
        actor_id=customer.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"provider": order.provider, "amount_paise": int(order.amount_paise)},
    )
    session.commit()

    # The mock adapter has no hosted page; route through our own sandbox screen so
    # the whole flow is demonstrable without a live gateway.
    if order.provider == "mock":
        return RedirectResponse(f"/pay/{invoice_id}/{link_key}/sandbox/{order.provider_order_id}", status_code=303)
    return render(
        request,
        "checkout_redirect.html",
        {
            "invoice": invoice,
            "customer": customer,
            "org": org,
            "checkout": checkout,
            "order_id": order.provider_order_id,
            "return_url": return_url,
            "link_key": link_key,
        },
        locale=org.locale,
        org=org,
    )


@router.get("/{invoice_id}/{link_key}/sandbox/{order_id}")
async def sandbox_checkout(
    invoice_id: str,
    link_key: str,
    order_id: str,
    request: Request,
    session: Session = Depends(db_session),
):
    """A local stand-in for the gateway's hosted page (mock adapter only)."""
    ensure_csrf(request)
    invoice, customer, org = _load(session, invoice_id, link_key)
    if get_settings().payment_provider not in {"mock", ""}:
        raise HTTPException(status_code=404, detail="not found")
    return render(
        request,
        "sandbox_checkout.html",
        {
            "invoice": invoice,
            "customer": customer,
            "org": org,
            "order_id": order_id,
            "link_key": link_key,
            "amount_paise": ledger.outstanding_of(invoice),
        },
        locale=org.locale,
        org=org,
    )


@router.post("/{invoice_id}/{link_key}/sandbox/{order_id}/complete")
async def sandbox_complete(
    invoice_id: str,
    link_key: str,
    order_id: str,
    request: Request,
    session: Session = Depends(db_session),
    outcome: str = Form("success"),
    csrf_token: str = Form(""),
):
    """Simulate the gateway calling us back. Uses the real webhook path."""
    verify_csrf(request, csrf_token)
    _invoice, _customer, org = _load(session, invoice_id, link_key)
    settings = get_settings()
    if settings.is_prod or settings.payment_provider not in {"mock", ""}:
        raise HTTPException(status_code=404, detail="not found")

    from app.adapters.payments import MockAdapter

    adapter = payment_service.get_adapter(org, settings)
    if not isinstance(adapter, MockAdapter):
        raise HTTPException(status_code=404, detail="not found")

    event_key = f"evt_{order_id}_{outcome}"
    body, headers = adapter.build_webhook(order_id=order_id, event_key=event_key, failed=(outcome != "success"))
    if outcome == "success":
        adapter.mark_paid(order_id)
    payment_service.process_webhook(
        session,
        provider=adapter.name,
        headers=headers,
        raw_body=body,
        org=org,
        settings=settings,
        ip=client_ip(request),
    )
    session.commit()
    return RedirectResponse(f"/pay/{invoice_id}/{link_key}/callback", status_code=303)


@router.get("/{invoice_id}/{link_key}/callback")
async def payment_callback(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
):
    """Return URL. We do NOT trust anything in the query string.

    The payment is only settled after the webhook and/or a server-side lookup
    confirms it, so this page simply reports the current state.
    """
    ensure_csrf(request)
    invoice, customer, org = _load(session, invoice_id, link_key)

    # Opportunistic verification: if a gateway order for this invoice is still
    # pending, re-check now so the customer sees the truth immediately instead of
    # waiting for the scheduled sweep.
    from sqlalchemy import select

    from app.models import GatewayOrder

    # Find THIS invoice's latest order, not merely the organisation's latest, so a
    # merchant with several open invoices cannot have the sweep pointed at the
    # wrong order by using another invoice's callback link.
    candidates = session.scalars(
        select(GatewayOrder)
        .where(GatewayOrder.org_id == org.id, GatewayOrder.purpose == "invoice")
        .order_by(GatewayOrder.created_at.desc())
        .limit(20)
    ).all()
    import json

    for candidate in candidates:
        if candidate.status not in {"created", "pending_verification"} or not candidate.notes:
            continue
        try:
            if json.loads(candidate.notes).get("invoice_id") != invoice.id:
                continue
        except (ValueError, TypeError):
            continue
        payment_service.reconcile_pending(
            session,
            min_age_minutes=0,
            limit=10,
            settings=get_settings(),
            org_id=org.id,
        )
        break

    session.commit()
    invoice = session.get(Invoice, invoice_id)
    return render(
        request,
        "pay_callback.html",
        {
            "invoice": invoice,
            "customer": customer,
            "org": org,
            "outstanding_paise": ledger.outstanding_of(invoice),
            "settled": ledger.outstanding_of(invoice) == 0,
            "link_key": link_key,
        },
        locale=org.locale,
        org=org,
    )


@router.post("/{invoice_id}/{link_key}/claim-paid")
async def claim_paid(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
    utr: str = Form(""),
    amount: str = Form(""),
    note: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice, customer, org = _load(session, invoice_id, link_key)
    dispute = Dispute(
        org_id=org.id,
        invoice_id=invoice.id,
        customer_id=customer.id,
        kind="claimed_paid",
        reason_code="customer_claims_paid",
        message=clean_text(note, max_length=1000) or None,
        claimed_utr=clean_text(utr, max_length=40) or None,
        status="open",
        expires_at=model_utcnow() + dt.timedelta(days=30),
    )
    session.add(dispute)
    session.flush()
    reminder_service.on_invoice_disputed(session, invoice)
    audit_service.record(
        session,
        action="portal.claimed_paid",
        org_id=org.id,
        actor_type="customer",
        actor_id=customer.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"utr": clean_text(utr, max_length=40)},
    )
    notifications.send(
        session,
        org=org,
        channel="email" if org.billing_email else "whatsapp",
        to=org.billing_email or (org.phone_e164 or ""),
        body=(
            f"{customer.name} says invoice {invoice.invoice_number} is already paid"
            + (f" (UTR {utr})." if utr else ".")
            + " Reminders have been paused — please confirm in the app."
        ),
        template="merchant_alert_claimed_paid",
        customer=None,
        related_type="invoice",
        related_id=invoice.id,
    )
    session.commit()
    return RedirectResponse(f"/pay/{invoice_id}/{link_key}?ok=claimed", status_code=303)


@router.post("/{invoice_id}/{link_key}/dispute")
async def raise_dispute(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
    reason_code: str = Form("other"),
    message: str = Form(""),
    claimed_amount: str = Form(""),
    promised_date: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice, customer, org = _load(session, invoice_id, link_key)
    allowed = {
        "work_not_done",
        "amount_incorrect",
        "already_paid",
        "needs_time",
        "po_number_missing",
        "gst_issue",
        "other",
    }
    code = reason_code if reason_code in allowed else "other"

    claimed_paise = None
    if claimed_amount.strip():
        try:
            from app.domain.money import rupees_to_paise

            claimed_paise = rupees_to_paise(claimed_amount)
        except ValueError:
            claimed_paise = None

    promised = None
    if promised_date.strip():
        try:
            promised = dt.date.fromisoformat(promised_date)
        except ValueError:
            promised = None

    kind = "part_payment_request" if code == "needs_time" else "dispute"
    dispute = Dispute(
        org_id=org.id,
        invoice_id=invoice.id,
        customer_id=customer.id,
        kind=kind,
        reason_code=code,
        message=clean_text(message, max_length=2000) or None,
        claimed_amount_paise=claimed_paise,
        promised_date=promised,
        status="open",
        expires_at=model_utcnow() + dt.timedelta(days=30),
    )
    session.add(dispute)
    session.flush()
    reminder_service.on_invoice_disputed(session, invoice)
    audit_service.record(
        session,
        action="portal.dispute_raised",
        org_id=org.id,
        actor_type="customer",
        actor_id=customer.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"reason": code},
    )
    notifications.send(
        session,
        org=org,
        channel="email" if org.billing_email else "whatsapp",
        to=org.billing_email or (org.phone_e164 or ""),
        body=(
            f"{customer.name} has responded on invoice {invoice.invoice_number}: "
            f"{code.replace('_', ' ')}. Reminders paused. See it in the app."
        ),
        template="merchant_alert_dispute",
        customer=None,
        related_type="invoice",
        related_id=invoice.id,
    )
    session.commit()
    return RedirectResponse(f"/pay/{invoice_id}/{link_key}?ok=dispute", status_code=303)


@router.post("/{invoice_id}/{link_key}/plan")
async def request_plan(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
    installments: str = Form("3"),
    first_date: str = Form(""),
    message: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice, customer, org = _load(session, invoice_id, link_key)

    try:
        count = max(2, min(12, int(installments)))
    except ValueError:
        count = 3

    outstanding = ledger.outstanding_of(invoice)
    if outstanding <= 0:
        return RedirectResponse(f"/pay/{invoice_id}/{link_key}", status_code=303)

    try:
        start = dt.date.fromisoformat(first_date) if first_date else today_ist() + dt.timedelta(days=7)
    except ValueError:
        start = today_ist() + dt.timedelta(days=7)
    if start < today_ist():
        start = today_ist()

    base = outstanding // count
    remainder = outstanding - base * count

    plan = InstallmentPlan(
        org_id=org.id,
        invoice_id=invoice.id,
        total_paise=outstanding,
        count=count,
        status="requested",
    )
    session.add(plan)
    session.flush()
    for index in range(count):
        amount = base + (remainder if index == count - 1 else 0)
        session.add(
            Installment(
                plan_id=plan.id,
                seq=index + 1,
                due_date=start + dt.timedelta(days=30 * index),
                amount_paise=amount,
                status="pending",
            )
        )
    session.flush()

    support = SupportRequest(
        org_id=org.id,
        subject_type="customer",
        subject_id=customer.id,
        channel="portal",
        category="part_payment",
        message=clean_text(message, max_length=2000)
        or f"Requests a {count}-instalment plan starting {start.isoformat()} for invoice {invoice.invoice_number}.",
        contact=customer.phone_e164 or customer.email or "",
        sla_due_at=model_utcnow() + dt.timedelta(hours=COMPLAINT_WINDOW_HOURS),
    )
    session.add(support)
    session.flush()
    reminder_service.on_invoice_disputed(session, invoice)

    audit_service.record(
        session,
        action="portal.plan_requested",
        org_id=org.id,
        actor_type="customer",
        actor_id=customer.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"count": count, "start": start.isoformat(), "outstanding_paise": outstanding},
    )
    notifications.send(
        session,
        org=org,
        channel="email" if org.billing_email else "whatsapp",
        to=org.billing_email or (org.phone_e164 or ""),
        body=(
            f"{customer.name} asked for a {count}-instalment plan on invoice {invoice.invoice_number} "
            f"({format_paise(outstanding)} outstanding), starting {start.isoformat()}. "
            "Reminders are paused until you respond."
        ),
        template="merchant_alert_plan_request",
        customer=None,
        related_type="invoice",
        related_id=invoice.id,
    )
    session.commit()
    return RedirectResponse(f"/pay/{invoice_id}/{link_key}?ok=plan", status_code=303)


@router.post("/{invoice_id}/{link_key}/support")
async def portal_support(
    invoice_id: str,
    link_key: str,
    request: Request,
    session: Session = Depends(db_session),
    category: str = Form("general"),
    message: str = Form(""),
    contact: str = Form(""),
    csrf_token: str = Form(""),
):
    """Grievance intake — this is the path a data-protection complaint also uses."""
    verify_csrf(request, csrf_token)
    _invoice, customer, org = _load(session, invoice_id, link_key)
    text = clean_text(message, max_length=4000)
    if not text:
        return RedirectResponse(f"/pay/{invoice_id}/{link_key}?error=empty", status_code=303)

    request_row = SupportRequest(
        org_id=org.id,
        subject_type="customer",
        subject_id=customer.id,
        channel="portal",
        category=category if category in {"general", "billing", "data", "complaint", "part_payment"} else "general",
        message=text,
        contact=clean_text(contact, max_length=254) or (customer.phone_e164 or customer.email or ""),
        sla_due_at=model_utcnow() + dt.timedelta(hours=COMPLAINT_WINDOW_HOURS),
    )
    session.add(request_row)
    session.flush()

    # Destination comes from the customer record only — never from the form.
    notifications.send_support_ack(
        session,
        org=org,
        customer=customer,
        locale=org.locale,
        reference=request_row.id[:8].upper(),
        sla_hours=COMPLAINT_WINDOW_HOURS,
    )
    notifications.send(
        session,
        org=org,
        channel="email" if org.billing_email else "whatsapp",
        to=org.billing_email or (org.phone_e164 or ""),
        body=f"New {category} request from {customer.name}: {text[:300]}",
        template="merchant_alert_support",
        customer=None,
        related_type="support_request",
        related_id=request_row.id,
    )
    audit_service.record(
        session,
        action="portal.support_requested",
        org_id=org.id,
        actor_type="customer",
        actor_id=customer.id,
        entity_type="support_request",
        entity_id=request_row.id,
        ip=client_ip(request),
        detail={"category": category},
    )
    session.commit()
    return RedirectResponse(f"/pay/{invoice_id}/{link_key}?ok=support", status_code=303)
