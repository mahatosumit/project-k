"""Customer routes: list, create, edit, consent management, reminders preview."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.gst import gstin_is_wellformed
from app.i18n import clean_text, normalise_phone
from app.models import Customer, Invoice, Organization, User
from app.services import audit as audit_service
from app.services import notifications
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

router = APIRouter(dependencies=[Depends(enforce_global_rate_limit)])


@router.get("/app/customers")
async def list_customers(
    request: Request,
    q: str = "",
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    query = select(Customer).where(Customer.org_id == org.id)
    term = clean_text(q, max_length=100)
    if term:
        like = f"%{term}%"
        query = query.where(
            func.lower(Customer.name).like(like.lower())
            | func.lower(func.coalesce(Customer.phone_e164, "")).like(like.lower())
            | func.lower(func.coalesce(Customer.email, "")).like(like.lower())
        )
    rows = session.scalars(query.order_by(Customer.name.asc()).limit(200)).all()

    # Per-customer outstanding, computed from the ledger not stored twice.
    from app.domain import ledger

    outstanding: dict[str, int] = {}
    for inv in session.scalars(
        select(Invoice).where(Invoice.org_id == org.id, Invoice.status.in_(["issued", "partly_paid"]))
    ).all():
        outstanding[inv.customer_id] = outstanding.get(inv.customer_id, 0) + ledger.outstanding_of(inv)

    return render(
        request,
        "customers.html",
        {"rows": rows, "q": term, "outstanding": outstanding, "user": user, "org": org},
        locale=org.locale,
        user=user,
        org=org,
    )


@router.get("/app/customers/new")
async def new_customer_form(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    return render(
        request,
        "customer_form.html",
        {"customer": None, "error": None, "user": user, "org": org},
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/app/customers")
async def create_customer(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    name: str = Form(""),
    contact_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    gstin: str = Form(""),
    state_code: str = Form(""),
    address: str = Form(""),
    notes: str = Form(""),
    whatsapp_opt_in: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    clean_name = clean_text(name, max_length=200)
    if not clean_name:
        return render(
            request,
            "customer_form.html",
            {"customer": None, "error": "form.required", "user": user, "org": org},
            status_code=400,
            locale=org.locale,
            user=user,
            org=org,
        )

    phone_e164 = None
    if phone.strip():
        phone_e164 = normalise_phone(phone)
        if phone_e164 is None:
            return render(
                request,
                "customer_form.html",
                {"customer": None, "error": "auth.bad_phone", "user": user, "org": org},
                status_code=400,
                locale=org.locale,
                user=user,
                org=org,
            )

    gstin_clean = (gstin or "").strip().upper() or None
    if gstin_clean and not gstin_is_wellformed(gstin_clean):
        return render(
            request,
            "customer_form.html",
            {"customer": None, "error": "settings.bad_gstin", "user": user, "org": org},
            status_code=400,
            locale=org.locale,
            user=user,
            org=org,
        )

    customer = Customer(
        org_id=org.id,
        name=clean_name,
        contact_name=clean_text(contact_name, max_length=200) or None,
        phone_e164=phone_e164,
        email=clean_text(email, max_length=254) or None,
        gstin=gstin_clean,
        state_code=(state_code.strip()[:2] or None),
        address=clean_text(address, max_length=400) or None,
        notes=clean_text(notes, max_length=2000) or None,
    )
    session.add(customer)
    session.flush()

    if whatsapp_opt_in and phone_e164:
        notifications.grant_consent(
            session,
            org_id=org.id,
            customer=customer,
            source="org_recorded",
            evidence=f"recorded by {user.email}",
        )

    audit_service.record(
        session,
        action="customer.created",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="customer",
        entity_id=customer.id,
        ip=client_ip(request),
    )
    session.commit()
    return RedirectResponse(f"/app/customers/{customer.id}", status_code=303)


@router.get("/app/customers/{customer_id}")
async def customer_detail(
    customer_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    customer = session.get(Customer, customer_id)
    if customer is None or customer.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")

    from app.domain import ledger

    invoices = session.scalars(
        select(Invoice).where(Invoice.customer_id == customer.id).order_by(Invoice.issue_date.desc()).limit(100)
    ).all()
    total_outstanding = sum(ledger.outstanding_of(i) for i in invoices)
    consent = notifications.has_consent(session, customer)

    return render(
        request,
        "customer_detail.html",
        {
            "customer": customer,
            "invoices": invoices,
            "outstanding_paise": total_outstanding,
            "consent": consent,
            "loan": None,
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/app/customers/{customer_id}/consent")
async def set_consent(
    customer_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    grant: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    customer = session.get(Customer, customer_id)
    if customer is None or customer.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")

    if grant == "yes":
        notifications.grant_consent(
            session, org_id=org.id, customer=customer, source="org_recorded", evidence=f"set by {user.email}"
        )
        action = "consent.granted"
    else:
        notifications.withdraw_consent(session, customer=customer)
        action = "consent.withdrawn"

    audit_service.record(
        session,
        action=action,
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="customer",
        entity_id=customer.id,
        ip=client_ip(request),
    )
    session.commit()
    return RedirectResponse(f"/app/customers/{customer.id}", status_code=303)
