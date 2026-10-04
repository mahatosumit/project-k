"""Reminder service: scheduling, dispatch, and the collector loop.

This is the product's engine. It ties together:

* the ladder definition (``app.domain.reminders``),
* consent-aware sending (``app.services.notifications``),
* ledger state (``app.domain.ledger``) — a settled invoice stops the ladder,
* the interest/evidence pack for the late stages (``app.domain.msmed``).

Dispatch is safe to run repeatedly and across workers: each reminder row is
claimed by a status transition, and a send is attempted under a small retry cap.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import ledger
from app.domain import reminders as ladder
from app.domain.money import today_ist
from app.models import Customer, Invoice, Organization, Reminder
from app.models import utcnow as model_utcnow
from app.services import audit as audit_service
from app.services import notifications
from app.services import portal as portal_service

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# Stages that must never be fired by a machine — a human sends the final notice.
HUMAN_ONLY_STAGES = {"final"}


@dataclass
class DispatchReport:
    attempted: int = 0
    sent: int = 0
    blocked_no_consent: int = 0
    failed: int = 0
    skipped_human_only: int = 0
    cancelled_settled: int = 0
    errors: list[str] = field(default_factory=list)


def pay_link_for(org: Organization, invoice: Invoice, customer: Customer | None = None) -> str:
    if customer is None:
        return f"{get_settings().base_url}/pay/{invoice.id}"
    return portal_service.portal_link(invoice, customer)


def plan_link_for(org: Organization, invoice: Invoice, customer: Customer | None = None) -> str:
    if customer is None:
        return f"{get_settings().base_url}/pay/{invoice.id}/plan"
    return portal_service.plan_link(invoice, customer)


def schedule_invoice(session: Session, invoice: Invoice, org: Organization | None = None) -> list[Reminder]:
    """Create the ladder for one invoice. Idempotent."""
    org = org or session.get(Organization, invoice.org_id)
    if org is None or invoice.status == "draft":
        return []
    return ladder.plan_for_invoice(session, invoice, org=org)


def on_invoice_settled(session: Session, invoice: Invoice) -> int:
    """Stop the ladder when money lands. Called from the payment path."""
    cancelled = ladder.cancel_pending(session, invoice)
    if cancelled:
        audit_service.record(
            session,
            action="reminders.cancelled_on_settlement",
            org_id=invoice.org_id,
            actor_type="system",
            entity_type="invoice",
            entity_id=invoice.id,
            detail={"cancelled": cancelled},
        )
    return cancelled


def on_invoice_disputed(session: Session, invoice: Invoice) -> int:
    """A dispute pauses the ladder: never dun someone who is talking to you."""
    cancelled = ladder.cancel_pending(session, invoice)
    session.flush()
    return cancelled


def dispatch_due(
    session: Session,
    *,
    limit: int = 100,
    now: dt.datetime | None = None,
    dry_run: bool = False,
) -> DispatchReport:
    """Send every reminder that is due. Safe to re-run; failures are retried."""
    report = DispatchReport()
    as_of = today_ist()
    for reminder in ladder.due_reminders(session, limit=limit, now=now):
        report.attempted += 1
        invoice = session.get(Invoice, reminder.invoice_id)
        if invoice is None:
            reminder.status = "cancelled"
            reminder.error = "invoice missing"
            continue

        if not ladder.is_step_sendable(reminder, invoice):
            reminder.status = "cancelled"
            reminder.error = "invoice settled or cancelled"
            report.cancelled_settled += 1
            continue

        if reminder.stage in HUMAN_ONLY_STAGES:
            # A person must review and send this one.
            reminder.status = "needs_human"
            reminder.error = "final notice requires human review before sending"
            report.skipped_human_only += 1
            continue

        customer = session.get(Customer, reminder.customer_id)
        org = session.get(Organization, reminder.org_id)
        if customer is None or org is None:
            reminder.status = "cancelled"
            reminder.error = "missing customer or organisation"
            continue

        locale = customer_locale(org, customer)
        context = ladder.context_for(
            invoice=invoice,
            customer=customer,
            org=org,
            pay_link=pay_link_for(org, invoice, customer),
            plan_link=plan_link_for(org, invoice, customer),
            as_of=as_of,
            locale=locale,
        )
        body = ladder.render(ladder.template_for_stage(reminder.stage), locale=locale, context=context)
        reminder.message_body = body

        if dry_run:
            continue

        destination = _destination_for(reminder.channel, customer)
        if not destination:
            reminder.status = "failed"
            reminder.error = f"no {reminder.channel} address on file"
            reminder.attempts += 1
            report.failed += 1
            continue

        outcome = notifications.send(
            session,
            org=org,
            channel=reminder.channel,
            to=destination,
            body=body,
            template=ladder.template_for_stage(reminder.stage),
            locale=locale,
            customer=customer if reminder.channel in {"whatsapp", "sms"} else None,
            related_type="invoice",
            related_id=invoice.id,
            actor="collector",
        )
        reminder.attempts += 1
        reminder.provider_message_id = outcome.provider_message_id
        reminder.error = outcome.error

        if outcome.ok:
            reminder.status = "sent"
            reminder.sent_at = model_utcnow()
            report.sent += 1
            audit_service.record(
                session,
                action="reminder.sent",
                org_id=org.id,
                actor_type="system",
                entity_type="invoice",
                entity_id=invoice.id,
                detail={"step": reminder.step_index, "stage": reminder.stage, "channel": reminder.channel},
            )
        elif outcome.status == "blocked_no_consent":
            reminder.status = "blocked_no_consent"
            report.blocked_no_consent += 1
        else:
            reminder.status = "failed" if reminder.attempts >= MAX_ATTEMPTS else "scheduled"
            report.failed += 1
            if reminder.attempts >= MAX_ATTEMPTS:
                audit_service.record(
                    session,
                    action="reminder.gave_up",
                    org_id=org.id,
                    actor_type="system",
                    entity_type="invoice",
                    entity_id=invoice.id,
                    detail={"step": reminder.step_index, "error": outcome.error},
                )
            if outcome.error:
                report.errors.append(f"{reminder.id}: {outcome.error}")

    session.flush()
    return report


def _destination_for(channel: str, customer: Customer) -> str | None:
    if channel in {"whatsapp", "sms"}:
        return customer.phone_e164 or None
    if channel == "email":
        return customer.email or None
    return None


def customer_locale(org: Organization, customer: Customer) -> str:
    """Customer's own choice wins; fall back to the organisation's default."""
    for candidate in (getattr(customer, "locale", None), org.locale, "en"):
        if candidate in ("en", "hi"):
            return candidate
    return "en"


def upcoming_for_org(session: Session, org_id: str, *, limit: int = 50) -> list[Reminder]:
    return list(
        session.scalars(
            select(Reminder)
            .where(Reminder.org_id == org_id, Reminder.status == "scheduled")
            .order_by(Reminder.scheduled_for.asc())
            .limit(limit)
        ).all()
    )


def history_for_invoice(session: Session, invoice_id: str) -> list[Reminder]:
    return list(
        session.scalars(
            select(Reminder)
            .where(Reminder.invoice_id == invoice_id)
            .order_by(Reminder.step_index.asc(), Reminder.scheduled_for.asc())
        ).all()
    )


def preview_ladder(
    session: Session,
    *,
    invoice: Invoice,
    org: Organization,
    locale: str = "en",
) -> list[dict[str, str]]:
    """The 'here is exactly what we will say' view — no sending, no guessing."""
    customer = session.get(Customer, invoice.customer_id)
    if customer is None:
        return []
    as_of = today_ist()
    context = ladder.context_for(
        invoice=invoice,
        customer=customer,
        org=org,
        pay_link=pay_link_for(org, invoice, customer),
        plan_link=plan_link_for(org, invoice, customer),
        as_of=as_of,
        locale=locale,
    )
    out: list[dict[str, str]] = []
    for step in ladder.steps_for(
        escalation_enabled=bool(org.reminder_escalation_enabled),
        reminder_days_before=int(org.reminder_days_before or 3),
        grace_days_before_final=int(org.grace_days_before_final or 7),
    ):
        when = invoice.due_date + dt.timedelta(days=step.offset_days)
        body = ladder.render(step.template, locale=locale, context=context)
        out.append(
            {
                "step": str(step.index),
                "stage": step.stage,
                "tone": step.tone,
                "channel": step.channel,
                "date": when.isoformat(),
                "body": body,
                "requires_human": "yes" if step.requires_human else "no",
            }
        )
    return out


def outstanding_summary(session: Session, org_id: str) -> dict[str, int]:
    invoices = session.scalars(
        select(Invoice).where(Invoice.org_id == org_id, Invoice.status.in_(["issued", "partly_paid"]))
    ).all()
    today = today_ist()
    total = 0
    overdue = 0
    rows: list[tuple[dt.date, int]] = []
    for inv in invoices:
        amount = ledger.outstanding_of(inv)
        if amount <= 0:
            continue
        total += amount
        rows.append((inv.due_date, amount))
        if inv.due_date < today:
            overdue += amount
    return {
        "outstanding_paise": total,
        "overdue_paise": overdue,
        "open_invoices": len(rows),
    }
