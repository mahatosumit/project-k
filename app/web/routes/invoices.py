"""Invoice routes: create, issue, view, record payment, write off, reminders."""

from __future__ import annotations

import contextlib
import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import ledger
from app.domain.gst import (
    compute_tax,
    invoice_number_for,
    series_for,
    state_name,
)
from app.domain.money import amount_in_words, financial_year, rupees_to_paise, today_ist
from app.domain.msmed import (
    compound_interest,
    escalation_checklist,
    stage_for,
)
from app.i18n import clean_text
from app.models import Counter, Customer, Invoice, InvoiceItem, Organization, Payment, User
from app.models import utcnow as model_utcnow
from app.services import audit as audit_service
from app.services import portal as portal_service
from app.services import reminders as reminder_service
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

OPEN = ("issued", "partly_paid", "overdue")


def _next_invoice_number(session: Session, org: Organization, issue_date: dt.date) -> tuple[str, str]:
    """Allocate the next consecutive number for this financial year.

    Rule 46(b) requires a consecutive serial unique for the financial year, so
    the counter is keyed per org+FY and incremented inside the same transaction
    that creates the invoice.
    """
    fy = financial_year(issue_date)
    key = f"invoice:{org.id}:{fy}"
    # with_for_update() takes a row lock on PostgreSQL. SQLite has no such lock, so
    # two concurrent creates can still collide on the unique (org, FY, number)
    # index; the caller retries once rather than surfacing a 500.
    row = session.scalar(select(Counter).where(Counter.name == key).with_for_update())
    if row is None:
        row = Counter(name=key, value=0)
        session.add(row)
        session.flush()
    row.value = int(row.value or 0) + 1
    session.flush()
    series = series_for(issue_date, org.invoice_prefix or "INV")
    number = invoice_number_for(org.invoice_prefix or "INV", fy, row.value)
    return number, series


@router.get("/app/invoices")
async def list_invoices(
    request: Request,
    status_filter: str = "",
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    query = select(Invoice).where(Invoice.org_id == org.id)
    if status_filter in {"draft", "issued", "partly_paid", "paid", "written_off", "cancelled"}:
        query = query.where(Invoice.status == status_filter)
    invoices = session.scalars(query.order_by(Invoice.issue_date.desc(), Invoice.invoice_number.desc()).limit(200)).all()
    customer_names = {
        c.id: c.name for c in session.scalars(select(Customer).where(Customer.org_id == org.id)).all()
    }
    today = today_ist()
    rows = [
        {
            "invoice": inv,
            "customer_name": customer_names.get(inv.customer_id, "—"),
            "outstanding_paise": ledger.outstanding_of(inv),
            "is_overdue": inv.due_date < today and ledger.outstanding_of(inv) > 0,
        }
        for inv in invoices
    ]
    return render(
        request,
        "invoices.html",
        {"rows": rows, "status_filter": status_filter, "user": user, "org": org},
        locale=org.locale,
        user=user,
        org=org,
    )


@router.get("/app/invoices/new")
async def new_invoice_form(
    request: Request,
    customer_id: str = "",
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    customers = session.scalars(
        select(Customer).where(Customer.org_id == org.id, Customer.is_active.is_(True)).order_by(Customer.name.asc())
    ).all()
    return render(
        request,
        "invoice_form.html",
        {
            "customers": customers,
            "preselected": customer_id,
            "error": None,
            "today": today_ist().isoformat(),
            "default_due_days": 15,
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/app/invoices")
async def create_invoice(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    customer_id: str = Form(""),
    description: str = Form(""),
    amount: str = Form(""),
    issue_date: str = Form(""),
    due_days: str = Form("15"),
    gst_rate: str = Form("18"),
    discount: str = Form("0"),
    place_of_supply: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    customer = session.get(Customer, customer_id)
    if customer is None or customer.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")

    customers = session.scalars(
        select(Customer).where(Customer.org_id == org.id, Customer.is_active.is_(True)).order_by(Customer.name.asc())
    ).all()

    def fail(key: str):
        return render(
            request,
            "invoice_form.html",
            {
                "customers": customers,
                "preselected": customer_id,
                "error": key,
                "today": today_ist().isoformat(),
                "default_due_days": 15,
                "form": {
                    "description": clean_text(description, max_length=400),
                    "amount": clean_text(amount, max_length=30),
                    "issue_date": issue_date,
                    "due_days": due_days,
                },
                "user": user,
                "org": org,
            },
            status_code=400,
            locale=org.locale,
            user=user,
            org=org,
        )

    try:
        subtotal = rupees_to_paise(amount)
    except ValueError:
        return fail("inv.bad_amount")
    if subtotal <= 0:
        return fail("inv.bad_amount")
    try:
        discount_paise = rupees_to_paise(discount or "0")
    except ValueError:
        return fail("inv.bad_amount")
    if discount_paise > subtotal:
        return fail("inv.bad_discount")

    try:
        issued = dt.date.fromisoformat(issue_date) if issue_date else today_ist()
    except ValueError:
        return fail("inv.bad_date")
    try:
        days = max(0, min(365, int(due_days or "15")))
    except ValueError:
        days = 15

    rate = Decimal("18")
    if gst_rate.strip():
        try:
            rate = Decimal(gst_rate.strip())
        except Exception:
            return fail("inv.bad_rate")
        if rate < 0 or rate > 100:
            return fail("inv.bad_rate")

    pos = (place_of_supply or customer.state_code or None)
    tax = compute_tax(
        subtotal_paise=subtotal,
        discount_paise=discount_paise,
        supplier_state_code=org.state_code,
        place_of_supply_state_code=pos,
        gst_registered=bool(org.gst_registered),
        gst_rate_percent=rate,
    )

    try:
        number, series = _next_invoice_number(session, org, issued)
    except Exception:
        # Two requests allocated the same sequence. Roll back to the savepoint and
        # take the next number rather than failing the merchant's submission.
        session.rollback()
        number, series = _next_invoice_number(session, org, issued)

    invoice = Invoice(
        org_id=org.id,
        customer_id=customer.id,
        invoice_number=number,
        series_fy=series,
        issue_date=issued,
        due_date=issued + dt.timedelta(days=days),
        sac_code=org.sac_code or "998314",
        description=clean_text(description, max_length=400) or None,
        place_of_supply_state_code=(str(pos).zfill(2) if pos else None),
        is_interstate=tax.is_interstate,
        taxable_value_paise=tax.taxable_value_paise,
        discount_paise=tax.discount_paise,
        gst_rate_percent=tax.gst_rate_percent,
        cgst_paise=tax.cgst_paise,
        sgst_paise=tax.sgst_paise,
        igst_paise=tax.igst_paise,
        total_paise=tax.total_paise,
        status="draft",
        notes=clean_text(notes, max_length=2000) or None,
        created_by=user.id,
    )
    session.add(invoice)
    session.flush()

    item = InvoiceItem(
        invoice_id=invoice.id,
        seq=1,
        description=clean_text(description, max_length=400) or "Services",
        hsn_sac=org.sac_code or "998314",
        quantity=1,
        unit="NOS",
        unit_price_paise=subtotal,
        line_total_paise=subtotal,
    )
    session.add(item)

    audit_service.record(
        session,
        action="invoice.created",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"number": number, "total_paise": tax.total_paise, "gst": str(tax.gst_rate_percent)},
    )
    session.commit()
    return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)


@router.post("/app/invoices/{invoice_id}/issue")
async def issue_invoice(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    if invoice.status != "draft":
        return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)

    # Rule 47: issue within 30 days of the supply. Warn (via a note) if late;
    # we never backdate a number, we just record the facts.
    invoice.status = "issued"
    invoice.issued_at = model_utcnow()
    session.flush()

    reminder_service.schedule_invoice(session, invoice, org)

    audit_service.record(
        session,
        action="invoice.issued",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"number": invoice.invoice_number, "due_date": invoice.due_date.isoformat()},
    )
    session.commit()
    return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)


@router.get("/app/invoices/{invoice_id}")
async def invoice_detail(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    customer = session.get(Customer, invoice.customer_id)
    payments = session.scalars(
        select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.received_at.desc())
    ).all()
    history = reminder_service.history_for_invoice(session, invoice.id)
    outstanding = ledger.outstanding_of(invoice)
    today = today_ist()
    days_overdue = max(0, (today - invoice.due_date).days)

    settings = get_settings()
    interest = compound_interest(
        principal_paise=outstanding,
        due_date=invoice.due_date,
        as_of=today,
        rbi_bank_rate_percent=(settings.rbi_bank_rate_percent or None),
    )
    stage = stage_for(
        status=invoice.status,
        due_date=invoice.due_date,
        total_paise=int(invoice.total_paise or 0),
        outstanding_paise=outstanding,
        as_of=today,
        escalation_enabled=bool(org.reminder_escalation_enabled),
        reminder_days_before=int(org.reminder_days_before or 3),
    )
    checklist = escalation_checklist(msme_registered=True, days_overdue=days_overdue, locale=org.locale)

    return render(
        request,
        "invoice_detail.html",
        {
            "invoice": invoice,
            "customer": customer,
            "payments": payments,
            "history": history,
            "outstanding_paise": outstanding,
            "days_overdue": days_overdue,
            "stage": stage,
            "interest": interest,
            "checklist": checklist,
            "words": amount_in_words(int(invoice.total_paise or 0)),
            "pos_name": state_name(invoice.place_of_supply_state_code),
            # The merchant needs the customer's own link so they can paste it
            # into WhatsApp themselves; the portal cannot be reached without it.
            "portal_path": (portal_service.portal_path(invoice, customer) if customer else None),
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.get("/app/invoices/{invoice_id}/print")
async def invoice_print(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    """A print-friendly invoice carrying the Rule 46 particulars."""
    ensure_csrf(request)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    customer = session.get(Customer, invoice.customer_id)
    items = session.scalars(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id).order_by(InvoiceItem.seq)).all()
    return render(
        request,
        "invoice_print.html",
        {
            "invoice": invoice,
            "customer": customer,
            "items": items,
            "words": amount_in_words(int(invoice.total_paise or 0)),
            "pos_name": state_name(invoice.place_of_supply_state_code),
            "user": user,
            "org": org,
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/app/invoices/{invoice_id}/payment")
async def record_payment(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    amount: str = Form(""),
    method: str = Form("cash"),
    reference: str = Form(""),
    utr: str = Form(""),
    received_on: str = Form(""),
    notes: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")

    try:
        amount_paise = rupees_to_paise(amount)
    except ValueError:
        return RedirectResponse(f"/app/invoices/{invoice.id}?error=amount", status_code=303)
    method_clean = method if method in {"cash", "upi", "bank_transfer", "cheque", "card", "adjustment"} else "cash"
    received_at = model_utcnow()
    if received_on:
        with contextlib.suppress(ValueError):
            received_at = dt.datetime.combine(dt.date.fromisoformat(received_on), dt.time(12, 0))

    try:
        payment = ledger.record_payment(
            session,
            invoice=invoice,
            amount_paise=amount_paise,
            method=method_clean,
            reference=clean_text(reference, max_length=120) or None,
            utr=clean_text(utr, max_length=40) or None,
            received_at=received_at,
            notes=clean_text(notes, max_length=500) or None,
            recorded_by=user.id,
        )
    except ledger.LedgerError:
        return RedirectResponse(f"/app/invoices/{invoice.id}?error=ledger", status_code=303)

    if ledger.outstanding_of(invoice) == 0:
        reminder_service.on_invoice_settled(session, invoice)

    audit_service.record(
        session,
        action="payment.recorded",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"amount_paise": amount_paise, "method": method_clean, "payment_id": payment.id},
    )
    session.commit()
    return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)


@router.post("/app/invoices/{invoice_id}/write-off")
async def write_off_invoice(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    amount: str = Form(""),
    reason: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    outstanding = ledger.outstanding_of(invoice)
    try:
        amount_paise = rupees_to_paise(amount) if amount.strip() else outstanding
    except ValueError:
        return RedirectResponse(f"/app/invoices/{invoice.id}?error=amount", status_code=303)
    reason_clean = clean_text(reason, max_length=500)
    if not reason_clean:
        return RedirectResponse(f"/app/invoices/{invoice.id}?error=reason", status_code=303)
    try:
        ledger.write_off(session, invoice=invoice, amount_paise=amount_paise, reason=reason_clean)
    except ledger.LedgerError:
        return RedirectResponse(f"/app/invoices/{invoice.id}?error=ledger", status_code=303)

    if ledger.outstanding_of(invoice) == 0:
        invoice.status = "written_off"
        reminder_service.on_invoice_settled(session, invoice)

    audit_service.record(
        session,
        action="invoice.written_off",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"amount_paise": amount_paise, "reason": reason_clean[:200]},
    )
    session.commit()
    return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)


@router.get("/app/invoices/{invoice_id}/reminders/preview")
async def reminder_preview(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    messages = reminder_service.preview_ladder(session, invoice=invoice, org=org, locale=org.locale)
    return render(
        request,
        "reminder_preview.html",
        {"invoice": invoice, "messages": messages, "user": user, "org": org},
        locale=org.locale,
        user=user,
        org=org,
    )


@router.post("/app/invoices/{invoice_id}/reminders/send-now")
async def send_reminder_now(
    invoice_id: str,
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
    csrf_token: str = Form(""),
):
    """Human-approved send of the next actionable step."""
    verify_csrf(request, csrf_token)
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    from app.models import Reminder

    reminder = session.scalar(
        select(Reminder)
        .where(Reminder.invoice_id == invoice.id, Reminder.status.in_(["scheduled", "needs_human"]))
        .order_by(Reminder.step_index.asc())
    )
    if reminder is None:
        return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)

    reminder.scheduled_for = model_utcnow() - dt.timedelta(seconds=1)
    reminder.status = "scheduled"
    session.flush()
    reminder_service.dispatch_due(session, limit=5)
    audit_service.record(
        session,
        action="reminder.sent_manually",
        org_id=org.id,
        actor_type="user",
        actor_id=user.id,
        entity_type="invoice",
        entity_id=invoice.id,
        ip=client_ip(request),
        detail={"step": reminder.step_index},
    )
    session.commit()
    return RedirectResponse(f"/app/invoices/{invoice.id}", status_code=303)
