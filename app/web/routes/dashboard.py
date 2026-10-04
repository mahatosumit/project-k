"""Authenticated dashboard: receivables at a glance, ageing, what needs a human."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import ledger
from app.domain.money import today_ist
from app.domain.msmed import stage_for
from app.models import Customer, Invoice, Organization, Payment, Reminder, SupportRequest, User
from app.web.deps import current_org, current_user, db_session, enforce_global_rate_limit, ensure_csrf
from app.web.templating import render

router = APIRouter(dependencies=[Depends(enforce_global_rate_limit)])


@router.get("/app")
async def dashboard(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    today = today_ist()

    invoices = session.scalars(
        select(Invoice).where(Invoice.org_id == org.id).order_by(Invoice.due_date.asc()).limit(500)
    ).all()

    outstanding = 0
    overdue = 0
    rows: list[dict] = []
    ageing = {"current": 0, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    needs_you: list[dict] = []

    for inv in invoices:
        amount = ledger.outstanding_of(inv)
        if amount <= 0:
            continue
        outstanding += amount
        if inv.due_date < today:
            overdue += amount
        days = (today - inv.due_date).days
        if days <= 0:
            ageing["current"] += amount
        elif days <= 30:
            ageing["1-30"] += amount
        elif days <= 60:
            ageing["31-60"] += amount
        elif days <= 90:
            ageing["61-90"] += amount
        else:
            ageing["90+"] += amount

        customer = session.get(Customer, inv.customer_id)
        rows.append(
            {
                "invoice": inv,
                "customer": customer,
                "outstanding_paise": amount,
                "stage": stage_for(
                    status=inv.status,
                    due_date=inv.due_date,
                    total_paise=int(inv.total_paise or 0),
                    outstanding_paise=amount,
                    as_of=today,
                    escalation_enabled=bool(org.reminder_escalation_enabled),
                    reminder_days_before=int(org.reminder_days_before or 3),
                ),
                "days_overdue": max(0, (today - inv.due_date).days),
            }
        )

    rows.sort(key=lambda r: (-r["days_overdue"], -(r["outstanding_paise"])))

    # Anything needing a person: blocked drafts, final notices, consent gaps,
    # unreviewed support requests, and payment orders stuck mid-flight.
    blocked = session.scalars(
        select(Reminder).where(Reminder.org_id == org.id, Reminder.status.in_(["needs_human", "blocked_no_consent"]))
    ).all()
    for rem in blocked[:10]:
        inv = session.get(Invoice, rem.invoice_id)
        cust = session.get(Customer, rem.customer_id)
        needs_you.append(
            {
                "kind": "needs_human" if rem.status == "needs_human" else "no_consent",
                "title": (
                    f"Final notice ready to send for {inv.invoice_number}" if rem.status == "needs_human"
                    else f"{cust.name if cust else 'A customer'} has no WhatsApp consent"
                ),
                "href": f"/app/invoices/{rem.invoice_id}",
            }
        )
    open_support = session.scalar(
        select(func.count()).select_from(SupportRequest).where(
            SupportRequest.org_id == org.id, SupportRequest.status == "open"
        )
    )
    if open_support:
        needs_you.append({"kind": "support", "title": f"{open_support} open customer request(s)", "href": "/app/support"})

    collected_30d = session.scalar(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.org_id == org.id,
            Payment.received_at >= dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=30),
        )
    )

    return render(
        request,
        "dashboard.html",
        {
            "org": org,
            "user": user,
            "totals": {
                "outstanding_paise": outstanding,
                "overdue_paise": overdue,
                "open_invoices": len(rows),
                "collected_30d_paise": int(collected_30d or 0),
            },
            "ageing": ageing,
            "rows": rows[:25],
            "needs_you": needs_you[:8],
            "gateway_connected": bool(org.gateway_provider),
        },
        locale=org.locale,
        user=user,
        org=org,
    )


@router.get("/app/support")
async def support_list(
    request: Request,
    session: Session = Depends(db_session),
    user: User = Depends(current_user),
    org: Organization = Depends(current_org),
):
    ensure_csrf(request)
    rows = session.scalars(
        select(SupportRequest)
        .where(SupportRequest.org_id == org.id)
        .order_by(SupportRequest.created_at.desc())
        .limit(100)
    ).all()
    return render(
        request,
        "support.html",
        {"rows": rows, "user": user, "org": org},
        locale=org.locale,
        user=user,
        org=org,
    )
