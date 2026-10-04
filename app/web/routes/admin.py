"""Admin routes: business settings, GST details, gateway connection, ops views.

The gateway credential fields are the highest-risk surface in the product, so:
* the values are written **encrypted at rest** and only ever read back masked,
* a change is audited without recording the value,
* an org can only ever see and edit its own row (checked on every load).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.gst import STATE_CODES, gstin_is_wellformed, pan_is_wellformed
from app.i18n import clean_text, normalise_locale, normalise_phone
from app.models import (
    AuditLog,
    BreachEvent,
    Customer,
    DataRequest,
    Invoice,
    NotificationLog,
    Organization,
    PaymentEvent,
    SupportRequest,
    User,
)
from app.models import utcnow as model_utcnow
from app.security import encrypt_secret, mask_secret
from app.services import audit as audit_service
from app.services import payments as payment_service
from app.services import ratelimit
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

router = APIRouter(prefix="/app/settings", dependencies=[Depends(enforce_global_rate_limit)])

PROVIDERS = {"razorpay": "Razorpay", "cashfree": "Cashfree"}


@router.get("")
async def settings_page(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    return render(
        request,
        "settings.html",
        {
            "states": STATE_CODES,
            "providers": PROVIDERS,
            "gateway_key_masked": mask_secret(org.gateway_key_id or "", keep=4),
            "has_gateway_key": bool(org.gateway_key_secret_enc),
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("")
async def save_settings(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    name: str = Form(""),
    legal_name: str = Form(""),
    gstin: str = Form(""),
    pan: str = Form(""),
    state_code: str = Form("27"),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    pincode: str = Form(""),
    billing_email: str = Form(""),
    phone: str = Form(""),
    locale: str = Form("en"),
    invoice_prefix: str = Form("INV"),
    sac_code: str = Form("998314"),
    gst_registered: str = Form(""),
    reminder_days_before: str = Form("3"),
    grace_days_before_final: str = Form("7"),
    reminder_escalation_enabled: str = Form(""),
    complaint_officer_name: str = Form(""),
    complaint_officer_email: str = Form(""),
    complaint_officer_phone: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)

    gstin_clean = (gstin or "").strip().upper()
    if gstin_clean and not gstin_is_wellformed(gstin_clean):
        return RedirectResponse("/app/settings?error=gstin", status_code=303)
    pan_clean = (pan or "").strip().upper()
    if pan_clean and not pan_is_wellformed(pan_clean):
        return RedirectResponse("/app/settings?error=pan", status_code=303)

    prefix = clean_text(invoice_prefix, max_length=10) or "INV"
    # Rule 46(b): the serial (prefix + FY + count) must fit in 16 characters.
    if len(prefix) > 8:
        return RedirectResponse("/app/settings?error=prefix", status_code=303)

    phone_e164 = normalise_phone(phone) if phone.strip() else None
    if phone.strip() and phone_e164 is None:
        return RedirectResponse("/app/settings?error=phone", status_code=303)

    officer_phone = normalise_phone(complaint_officer_phone) if complaint_officer_phone.strip() else None

    org.name = clean_text(name, max_length=200) or org.name
    org.legal_name = clean_text(legal_name, max_length=200) or None
    org.gstin = gstin_clean or None
    org.pan = pan_clean or None
    org.state_code = (state_code.strip()[:2] or "27").zfill(2)
    org.address_line1 = clean_text(address_line1, max_length=200) or None
    org.address_line2 = clean_text(address_line2, max_length=200) or None
    org.city = clean_text(city, max_length=100) or None
    org.state = clean_text(state, max_length=100) or None
    org.pincode = "".join(ch for ch in pincode if ch.isdigit())[:6] or None
    org.billing_email = clean_text(billing_email, max_length=254) or None
    org.phone_e164 = phone_e164
    org.locale = normalise_locale(locale)
    org.invoice_prefix = prefix
    org.sac_code = (sac_code.strip()[:6] or "998314")
    org.gst_registered = bool(gst_registered)
    try:
        org.reminder_days_before = max(0, min(30, int(reminder_days_before or "3")))
    except ValueError:
        org.reminder_days_before = 3
    try:
        org.grace_days_before_final = max(0, min(90, int(grace_days_before_final or "7")))
    except ValueError:
        org.grace_days_before_final = 7
    org.reminder_escalation_enabled = bool(reminder_escalation_enabled)
    org.complaint_officer_name = clean_text(complaint_officer_name, max_length=200) or None
    org.complaint_officer_email = clean_text(complaint_officer_email, max_length=254) or None
    org.complaint_officer_phone = officer_phone
    org.updated_at = model_utcnow()
    session.flush()

    audit_service.record(
        session,
        action="org.settings_updated",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="organization",
        entity_id=org.id,
        ip=client_ip(request),
        detail={"gst_registered": bool(org.gst_registered), "locale": org.locale, "sac": org.sac_code},
    )
    session.commit()
    return RedirectResponse("/app/settings?ok=saved", status_code=303)


@router.post("/gateway")
async def save_gateway(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    provider: str = Form(""),
    key_id: str = Form(""),
    key_value: str = Form(""),
    webhook_value: str = Form(""),
    action: str = Form("save"),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)

    if action == "disconnect":
        org.gateway_provider = None
        org.gateway_key_id = None
        org.gateway_key_secret_enc = None
        org.gateway_webhook_secret_enc = None
        org.gateway_status = "not_connected"
        org.updated_at = model_utcnow()
        session.flush()
        audit_service.record(
            session,
            action="gateway.disconnected",
            org_id=org.id,
            actor_type="user",
            actor_id=user.id,
            entity_type="organization",
            entity_id=org.id,
            ip=client_ip(request),
        )
        session.commit()
        return RedirectResponse("/app/settings?ok=gateway_removed", status_code=303)

    provider_clean = provider.strip().lower()
    if provider_clean not in PROVIDERS:
        return RedirectResponse("/app/settings?error=provider", status_code=303)
    if not key_id.strip():
        return RedirectResponse("/app/settings?error=keyid", status_code=303)

    org.gateway_provider = provider_clean
    org.gateway_key_id = clean_text(key_id, max_length=120)
    if key_value.strip():
        org.gateway_key_secret_enc = encrypt_secret(key_value.strip())
    if webhook_value.strip():
        org.gateway_webhook_secret_enc = encrypt_secret(webhook_value.strip())
    org.gateway_status = "connected" if org.gateway_key_secret_enc else "keys_incomplete"
    org.updated_at = model_utcnow()
    session.flush()

    # Audit the fact of the change, never the credential itself.
    audit_service.record(
        session,
        action="gateway.connected",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="organization",
        entity_id=org.id,
        ip=client_ip(request),
        detail={
            "provider": provider_clean,
            "key_id_masked": mask_secret(org.gateway_key_id, keep=4),
            "key_replaced": bool(key_value.strip()),
            "webhook_replaced": bool(webhook_value.strip()),
        },
    )
    session.commit()
    return RedirectResponse("/app/settings?ok=gateway_saved", status_code=303)


@router.post("/gateway/test")
async def test_gateway(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    csrf_token: str = Form(""),
):
    """Ask the gateway to create a tiny sandbox order, proving the keys work.

    This is the safest possible live check: it uses the configured mode, so in
    production it would still create an order that nobody pays.
    """
    verify_csrf(request, csrf_token)
    from app.adapters.payments import OrderRequest, PaymentError

    adapter = payment_service.get_adapter(org, get_settings())
    try:
        result = adapter.create_order(
            OrderRequest(amount_paise=100, receipt=f"keytest-{org.id[:6]}", notes={"purpose": "key_test"})
        )
        detail = {"ok": True, "provider": adapter.name, "order_id": result.provider_order_id}
    except PaymentError as exc:
        detail = {"ok": False, "provider": adapter.name, "error": str(exc)}
    except Exception as exc:
        detail = {"ok": False, "provider": adapter.name, "error": type(exc).__name__}

    audit_service.record(
        session,
        action="gateway.key_test",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="organization",
        entity_id=org.id,
        ip=client_ip(request),
        detail=detail,
    )
    session.commit()
    return RedirectResponse("/app/settings?ok=keytest" if detail.get("ok") else "/app/settings?error=keytest", status_code=303)


# --- Ops views ------------------------------------------------------------

ops_router = APIRouter(prefix="/app/ops", dependencies=[Depends(enforce_global_rate_limit)])


@ops_router.get("")
async def ops_page(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    ws = model_utcnow() - dt.timedelta(days=7)
    # EVERY list on this page is scoped to the caller's own organisation. A
    # tenant must never see another tenant's webhook payloads, audit trail,
    # data-subject requests or incident records (security review, H1).
    counts = {
        "invoices": session.scalar(select(func.count()).select_from(Invoice).where(Invoice.org_id == org.id)),
        "customers": session.scalar(select(func.count()).select_from(Customer).where(Customer.org_id == org.id)),
        "notifications_7d": session.scalar(
            select(func.count())
            .select_from(NotificationLog)
            .where(NotificationLog.created_at >= ws, NotificationLog.org_id == org.id)
        ),
        "support_open": session.scalar(
            select(func.count()).select_from(SupportRequest).where(
                SupportRequest.org_id == org.id, SupportRequest.status == "open"
            )
        ),
    }
    webhook_events = session.scalars(
        select(PaymentEvent)
        .where(PaymentEvent.org_id == org.id)
        .order_by(PaymentEvent.received_at.desc())
        .limit(25)
    ).all()
    audit_rows = session.scalars(
        select(AuditLog).where(AuditLog.org_id == org.id).order_by(AuditLog.created_at.desc()).limit(40)
    ).all()
    breaches = session.scalars(
        select(BreachEvent).where(BreachEvent.org_id == org.id).order_by(BreachEvent.detected_at.desc()).limit(10)
    ).all()
    data_requests = session.scalars(
        select(DataRequest)
        .where(DataRequest.org_id == org.id)
        .order_by(DataRequest.requested_at.desc())
        .limit(20)
    ).all()
    settings = get_settings()
    return render(
        request,
        "ops.html",
        {
            "counts": counts,
            "webhook_events": webhook_events,
            "audit_rows": audit_rows,
            "breaches": breaches,
            "data_requests": data_requests,
            "cert_in_hours": settings.cert_in_report_hours,
            "log_retention_days": settings.log_retention_days,
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@ops_router.post("/run/reconcile")
async def run_reconcile(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    # Scoped to this organisation: a tenant button must never act on another
    # tenant's gateway orders. The full-platform sweep runs from the scheduler.
    summary = payment_service.daily_reconciliation(session, settings=get_settings(), org_id=org.id)
    audit_service.record(
        session,
        action="ops.reconcile_run",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        ip=client_ip(request),
        detail=summary,
    )
    session.commit()
    return RedirectResponse("/app/ops?ok=reconciled", status_code=303)


@ops_router.post("/run/maintenance")
async def run_maintenance(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    pruned_counters = ratelimit.prune(session)
    pruned_audit = audit_service.prune_audit(session)
    audit_service.record(
        session,
        action="ops.maintenance_run",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        ip=client_ip(request),
        detail={"counters_pruned": pruned_counters, "audit_pruned": pruned_audit},
    )
    session.commit()
    return RedirectResponse("/app/ops?ok=maintained", status_code=303)


@ops_router.post("/data-request")
async def create_data_request(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    customer_id: str = Form(""),
    kind: str = Form("export"),
    note: str = Form(""),
    csrf_token: str = Form(""),
):
    """Record a data-principal request (export or erasure) with its due date."""
    verify_csrf(request, csrf_token)
    customer = session.get(Customer, customer_id)
    if customer is None or customer.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    row = DataRequest(
        org_id=org.id,
        subject_type="customer",
        subject_id=customer.id,
        kind=kind if kind in {"export", "erase", "correct"} else "export",
        status="received",
        note=clean_text(note, max_length=2000) or None,
        due_at=model_utcnow() + dt.timedelta(days=30),
    )
    session.add(row)
    session.flush()
    audit_service.record(
        session,
        action="dpr.request_received",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="data_request",
        entity_id=row.id,
        ip=client_ip(request),
        detail={"kind": row.kind},
    )
    session.commit()
    return RedirectResponse("/app/ops?ok=data_request", status_code=303)


@ops_router.get("/export/customer/{customer_id}")
async def export_customer_data(
    customer_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    """A machine-readable export of everything we hold about one customer."""
    from fastapi.responses import JSONResponse

    customer = session.get(Customer, customer_id)
    if customer is None or customer.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")

    invoices = session.scalars(select(Invoice).where(Invoice.customer_id == customer.id)).all()
    from app.models import Consent, Dispute, Payment, Reminder

    payload = {
        "generated_at": model_utcnow().isoformat() + "Z",
        "controller": {"name": org.name, "email": org.billing_email, "grievance_officer": org.complaint_officer_email},
        "subject": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone_e164,
            "email": customer.email,
            "gstin": customer.gstin,
            "address": customer.address,
        },
        "consents": [
            {
                "purpose": c.purpose,
                "granted": c.granted,
                "notice_version": c.notice_version,
                "source": c.source,
                "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
            }
            for c in session.scalars(select(Consent).where(Consent.subject_id == customer.id)).all()
        ],
        "invoices": [
            {
                "number": i.invoice_number,
                "issue_date": i.issue_date.isoformat(),
                "due_date": i.due_date.isoformat(),
                "total_paise": int(i.total_paise or 0),
                "paid_paise": int(i.paid_paise or 0),
                "status": i.status,
            }
            for i in invoices
        ],
        "payments": [
            {
                "amount_paise": int(p.amount_paise),
                "method": p.method,
                "reference": p.reference,
                "received_at": p.received_at.isoformat(),
            }
            for p in session.scalars(select(Payment).where(Payment.customer_id == customer.id)).all()
        ],
        "reminders": [
            {
                "step": r.step_index,
                "stage": r.stage,
                "channel": r.channel,
                "status": r.status,
                "scheduled_for": r.scheduled_for.isoformat(),
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            }
            for r in session.scalars(select(Reminder).where(Reminder.customer_id == customer.id)).all()
        ],
        "disputes": [
            {
                "kind": d.kind,
                "reason_code": d.reason_code,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
            }
            for d in session.scalars(select(Dispute).where(Dispute.customer_id == customer.id)).all()
        ],
    }
    audit_service.record(
        session,
        action="dpr.export_generated",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="customer",
        entity_id=customer.id,
        ip=client_ip(request),
    )
    session.commit()
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="customer-{customer.id[:8]}-export.json"', "Cache-Control": "no-store"},
    )


@ops_router.post("/data-request/{request_id}/complete")
async def complete_data_request(
    request_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    note: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    row = session.get(DataRequest, request_id)
    if row is None or row.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    row.status = "completed"
    row.completed_at = model_utcnow()
    row.note = (row.note or "") + ("\n" + clean_text(note, max_length=1000) if note else "")
    session.flush()
    audit_service.record(
        session,
        action="dpr.completed",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="data_request",
        entity_id=row.id,
        ip=client_ip(request),
        detail={"kind": row.kind},
    )
    session.commit()
    return RedirectResponse("/app/ops?ok=data_done", status_code=303)


@ops_router.post("/breach")
async def record_breach(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    severity: str = Form("medium"),
    summary: str = Form(""),
    affected: str = Form("0"),
    csrf_token: str = Form(""),
):
    """Start the incident clock. CERT-In requires reporting within 6 hours."""
    verify_csrf(request, csrf_token)
    settings = get_settings()
    detected = model_utcnow()
    row = BreachEvent(
        org_id=org.id,
        severity=severity if severity in {"low", "medium", "high", "critical"} else "medium",
        summary=clean_text(summary, max_length=4000) or "unspecified",
        detected_at=detected,
        report_due_at=detected + dt.timedelta(hours=settings.cert_in_report_hours),
        affected_subjects=max(0, int(affected or 0)) if str(affected).isdigit() else 0,
        status="open",
    )
    session.add(row)
    session.flush()
    audit_service.record(
        session,
        action="breach.recorded",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="breach_event",
        entity_id=row.id,
        ip=client_ip(request),
        detail={"severity": row.severity, "due": row.report_due_at.isoformat()},
    )
    session.commit()
    return RedirectResponse("/app/ops?ok=breach", status_code=303)
