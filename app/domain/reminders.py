"""The reminder ladder: the core value loop of the product.

Design notes
------------
* Steps are **scheduled rows**, not in-request sends. The collector process
  picks up due rows, so a page render never sends a message and a failure in
  one channel does not lose the ladder.
* Every step is idempotent by ``(invoice_id, step_index, channel)`` — the
  database unique index makes a duplicate schedule impossible even if two
  workers race.
* Messages are composed from templates in ``app/i18n`` so a new locale is a new
  string table, not a code change.
* Calling someone's boss is *not* part of the ladder. Escalation means tone and
  legal framing, never third-party shaming, and the human always presses send
  for the legal stage.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.ledger import outstanding_of
from app.domain.money import format_paise, format_paise_plain
from app.models import Customer, Invoice, Organization, Reminder
from app.models import utcnow as model_utcnow


@dataclass(frozen=True)
class LadderStep:
    index: int
    stage: str
    offset_days: int          # relative to due date; negative = before due
    tone: str                 # friendly | firm | formal | final
    channel: str              # whatsapp | sms | email
    template: str
    requires_human: bool = False


# The ladder. Nine touches over ~4 months, then it stops and hands to a human.
LADDER: tuple[LadderStep, ...] = (
    LadderStep(0, "pre_due", -3, "friendly", "whatsapp", "reminder_pre_due"),
    LadderStep(1, "due_today", 0, "friendly", "whatsapp", "reminder_due_today"),
    LadderStep(2, "overdue_3", 3, "friendly", "whatsapp", "reminder_overdue_3"),
    LadderStep(3, "overdue_7", 7, "firm", "whatsapp", "reminder_overdue_7"),
    LadderStep(4, "overdue_14", 14, "firm", "whatsapp", "reminder_overdue_14"),
    LadderStep(5, "overdue_21", 21, "firm", "sms", "reminder_overdue_21_sms"),
    LadderStep(6, "overdue_30", 30, "formal", "whatsapp", "reminder_overdue_30"),
    LadderStep(7, "overdue_45", 45, "formal", "whatsapp", "reminder_msmed_45"),
    LadderStep(8, "overdue_60", 60, "final", "email", "reminder_final_notice", requires_human=True),
)


def steps_for(
    *,
    escalation_enabled: bool = True,
    reminder_days_before: int = 3,
    grace_days_before_final: int = 7,
) -> list[LadderStep]:
    """The ladder actually applied to one organisation."""
    steps: list[LadderStep] = []
    for step in LADDER:
        if not escalation_enabled and step.index > 3:
            continue
        if step.index == 0:
            steps.append(
                LadderStep(
                    step.index,
                    step.stage,
                    -max(0, int(reminder_days_before)),
                    step.tone,
                    step.channel,
                    step.template,
                    step.requires_human,
                )
            )
            continue
        if step.index == 8:
            steps.append(
                LadderStep(
                    step.index,
                    step.stage,
                    step.offset_days + max(0, int(grace_days_before_final) - 7),
                    step.tone,
                    step.channel,
                    step.template,
                    step.requires_human,
                )
            )
            continue
        steps.append(step)
    return steps


# Stage name -> template key. Unique per step, which is why a reminder stores the
# stage and resolves its template here instead of duplicating strings everywhere.
TEMPLATE_BY_STAGE: dict[str, str] = {
    "pre_due": "reminder_pre_due",
    "due_today": "reminder_due_today",
    "overdue_3": "reminder_overdue_3",
    "overdue_7": "reminder_overdue_7",
    "overdue_14": "reminder_overdue_14",
    "overdue_21": "reminder_overdue_21_sms",
    "overdue_30": "reminder_overdue_30",
    "overdue_45": "reminder_msmed_45",
    "overdue_60": "reminder_final_notice",
}


def template_for_stage(stage: str) -> str:
    return TEMPLATE_BY_STAGE.get(stage, "reminder_overdue_3")


def schedule_datetime(due_date: dt.date, offset_days: int) -> dt.datetime:
    """Anchor a step at 10:00 IST on the offset day, stored as UTC naive."""
    day = due_date + dt.timedelta(days=offset_days)
    ist_10 = dt.datetime.combine(day, dt.time(hour=10, minute=0))
    return ist_10 - dt.timedelta(hours=5, minutes=30)


def plan_for_invoice(
    session: Session,
    invoice: Invoice,
    *,
    org: Organization,
    channel_override: str | None = None,
    now: dt.datetime | None = None,
) -> list[Reminder]:
    """Create any missing ladder rows for an invoice; return the full ladder.

    Existing rows are never duplicated or reset, so calling this repeatedly is
    safe (for example after editing the invoice).
    """
    now = now or model_utcnow()
    existing = {
        (r.step_index, r.channel): r
        for r in session.scalars(select(Reminder).where(Reminder.invoice_id == invoice.id))
    }
    created: list[Reminder] = []
    steps = steps_for(
        escalation_enabled=bool(org.reminder_escalation_enabled),
        reminder_days_before=int(org.reminder_days_before or 3),
        grace_days_before_final=int(org.grace_days_before_final or 7),
    )
    for step in steps:
        channel = channel_override or step.channel
        key = (step.index, channel)
        if key in existing:
            created.append(existing[key])
            continue
        reminder = Reminder(
            org_id=invoice.org_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            step_index=step.index,
            stage=step.stage,
            channel=channel,
            tone=step.tone,
            scheduled_for=schedule_datetime(invoice.due_date, step.offset_days),
            status="scheduled",
        )
        session.add(reminder)
        created.append(reminder)
    session.flush()
    return created


def due_reminders(session: Session, *, limit: int = 200, now: dt.datetime | None = None) -> list[Reminder]:
    now = now or model_utcnow()
    rows = session.scalars(
        select(Reminder)
        .where(Reminder.status == "scheduled", Reminder.scheduled_for <= now)
        .order_by(Reminder.scheduled_for.asc())
        .limit(limit)
    ).all()
    return list(rows)


def cancel_pending(session: Session, invoice: Invoice) -> int:
    """Stop the ladder (invoice settled, disputed, or written off)."""
    rows = session.scalars(
        select(Reminder).where(Reminder.invoice_id == invoice.id, Reminder.status == "scheduled")
    ).all()
    for row in rows:
        row.status = "cancelled"
        row.updated_at = model_utcnow()
    session.flush()
    return len(rows)


def is_step_sendable(reminder: Reminder, invoice: Invoice) -> bool:
    """Guard before sending: settled or cancelled invoices stop the ladder."""
    if invoice.status in {"paid", "cancelled", "written_off", "draft"}:
        return False
    return outstanding_of(invoice) > 0


# --- Message rendering -----------------------------------------------------

# Tone is deliberately polite-by-default. Nothing here threatens, shames, or
# implies legal action; the formal steps state facts and the statutory route.
TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "reminder_pre_due": (
            "Namaste {contact},\n\n"
            "A gentle heads-up: invoice {invoice_no} for {amount} is due on {due_date}.\n"
            "{description_line}"
            "\nYou can see the details and pay here: {pay_link}\n\n"
            "If a part payment or a different date would help, reply here and we will set it up.\n\n"
            "Thank you,\n{org_name}\n{org_contact}"
        ),
        "reminder_due_today": (
            "Namaste {contact},\n\n"
            "Invoice {invoice_no} for {amount} is due today ({due_date}).\n\n"
            "Pay here: {pay_link}\n\n"
            "Already paid? Reply with the UTR or a screenshot and we will update it today.\n\n"
            "Thank you,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_3": (
            "Namaste {contact},\n\n"
            "Invoice {invoice_no} for {amount} was due on {due_date} and is {days_overdue} days past due. "
            "The balance outstanding is {outstanding}.\n\n"
            "Pay here: {pay_link}\n\n"
            "If there is an issue with the invoice, tell us what it is and we will fix it. "
            "A split payment is also fine — reply and we will send a plan.\n\n"
            "Thank you,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_7": (
            "Namaste {contact},\n\n"
            "Following up on invoice {invoice_no} ({amount}), now {days_overdue} days past due. "
            "Outstanding: {outstanding}.\n\n"
            "Pay here: {pay_link}\n\n"
            "Please confirm a payment date, or reply with the UTR if it has already been paid.\n\n"
            "Regards,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_14": (
            "Namaste {contact},\n\n"
            "Invoice {invoice_no} for {amount} is {days_overdue} days past its due date of {due_date}. "
            "Outstanding balance: {outstanding}.\n\n"
            "Pay in full here: {pay_link}\n"
            "Or set up a part payment: {plan_link}\n\n"
            "We would like to resolve this directly and quickly. Please reply with a date.\n\n"
            "Regards,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_21_sms": (
            "{org_name}: Invoice {invoice_no} of {amount} is {days_overdue} days overdue. "
            "Outstanding {outstanding}. Pay: {pay_link} . Reply for a part-payment plan."
        ),
        "reminder_overdue_30": (
            "Namaste {contact},\n\n"
            "Invoice {invoice_no} ({amount}) is now {days_overdue} days past due. "
            "Outstanding: {outstanding}.\n\n"
            "Pay here: {pay_link}\n"
            "Part-payment plan: {plan_link}\n\n"
            "Please treat this as a formal request for payment. If you believe this "
            "invoice is incorrect, tell us the reason and the amount in dispute so we can "
            "correct our records.\n\n"
            "Regards,\n{org_name}\n{org_contact}"
        ),
        "reminder_msmed_45": (
            "Namaste {contact},\n\n"
            "Invoice {invoice_no} for {amount} has been unpaid for {days_overdue} days. "
            "Under the MSMED Act, 2006 a buyer is required to pay a registered micro or "
            "small enterprise within 45 days, and interest can become payable after that.\n\n"
            "Outstanding is {outstanding}. "
            "Please pay here: {pay_link}\n"
            "Or agree a plan: {plan_link}\n\n"
            "We would much rather settle this with you than take any formal step. "
            "Please reply with a payment date today.\n\n"
            "Regards,\n{org_name}\n{org_contact}"
        ),
        "reminder_final_notice": (
            "Subject: Final request for payment — invoice {invoice_no} ({amount})\n\n"
            "Dear {contact},\n\n"
            "Invoice {invoice_no} dated {issue_date}, for {amount}, fell due on {due_date} "
            "and remains unpaid {days_overdue} days later. The outstanding balance is {outstanding}.\n\n"
            "We have written to you on several occasions. This is a final request before we "
            "consider the recovery options available to us, which may include the MSME "
            "Samadhaan / MSEFC route where applicable.\n\n"
            "To settle: {pay_link}\n"
            "A statement of account and copies of the invoices are attached for your records.\n\n"
            "If payment has already been made, please share the UTR so we can close this today.\n\n"
            "Regards,\n{org_name}\n{org_contact}"
        ),
    },
    "hi": {
        "reminder_pre_due": (
            "नमस्ते {contact},\n\n"
            "याद दिलाने के लिए: चालान {invoice_no}, राशि {amount}, देय तिथि {due_date}.\n"
            "{description_line}"
            "\nविवरण और भुगतान यहाँ: {pay_link}\n\n"
            "अगर आंशिक भुगतान या कोई और तारीख ठीक रहे, तो यहीं जवाब दें — हम व्यवस्था कर देंगे.\n\n"
            "धन्यवाद,\n{org_name}\n{org_contact}"
        ),
        "reminder_due_today": (
            "नमस्ते {contact},\n\n"
            "चालान {invoice_no}, राशि {amount}, आज ({due_date}) देय है.\n\n"
            "भुगतान यहाँ: {pay_link}\n\n"
            "भुगतान हो चुका है? UTR या स्क्रीनशॉट भेजें, हम आज ही दर्ज कर देंगे.\n\n"
            "धन्यवाद,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_3": (
            "नमस्ते {contact},\n\n"
            "चालान {invoice_no} ({amount}) की देय तिथि {due_date} थी और अब {days_overdue} दिन बकाया है. "
            "शेष राशि: {outstanding}.\n\n"
            "भुगतान यहाँ: {pay_link}\n\n"
            "चालान में कोई दिक्कत है तो बताइए, हम ठीक कर देंगे. आंशिक भुगतान भी चलेगा — "
            "जवाब दें, हम योजना भेज देंगे.\n\n"
            "धन्यवाद,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_7": (
            "नमस्ते {contact},\n\n"
            "चालान {invoice_no} ({amount}) अब {days_overdue} दिन बकाया है. शेष: {outstanding}.\n\n"
            "भुगतान यहाँ: {pay_link}\n\n"
            "कृपया भुगतान की तारीख बताएं, या भुगतान हो गया हो तो UTR भेज दें.\n\n"
            "सादर,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_14": (
            "नमस्ते {contact},\n\n"
            "चालान {invoice_no} ({amount}) अपनी देय तिथि {due_date} से {days_overdue} दिन बकाया है. "
            "शेष राशि: {outstanding}.\n\n"
            "पूरा भुगतान: {pay_link}\n"
            "आंशिक भुगतान योजना: {plan_link}\n\n"
            "हम यह मामला सीधे और जल्दी सुलझाना चाहते हैं. कृपया तारीख बताएं.\n\n"
            "सादर,\n{org_name}\n{org_contact}"
        ),
        "reminder_overdue_21_sms": (
            "{org_name}: चालान {invoice_no}, राशि {amount}, {days_overdue} दिन बकाया. "
            "शेष {outstanding}. भुगतान: {pay_link} . आंशिक भुगतान के लिए जवाब दें."
        ),
        "reminder_overdue_30": (
            "नमस्ते {contact},\n\n"
            "चालान {invoice_no} ({amount}) अब {days_overdue} दिन बकाया है. शेष: {outstanding}.\n\n"
            "भुगतान: {pay_link}\n"
            "आंशिक भुगतान योजना: {plan_link}\n\n"
            "कृपया इसे भुगतान की औपचारिक मांग मानें. अगर चालान गलत लगता है तो कारण और "
            "विवादित राशि बताएं, ताकि हम रिकॉर्ड सुधार सकें.\n\n"
            "सादर,\n{org_name}\n{org_contact}"
        ),
        "reminder_msmed_45": (
            "नमस्ते {contact},\n\n"
            "चालान {invoice_no} ({amount}) {days_overdue} दिनों से अवैतनिक है. MSMED अधिनियम, 2006 के "
            "अनुसार क्रेता को पंजीकृत सूक्ष्म/लघु उद्यम को 45 दिनों के भीतर भुगतान करना होता है, "
            "और उसके बाद ब्याज देय हो सकता है.\n\n"
            "शेष राशि {outstanding}. भुगतान: {pay_link}\n"
            "या योजना तय करें: {plan_link}\n\n"
            "हम इसे औपचारिक कदम उठाने की बजाय आपके साथ सुलझाना चाहेंगे. "
            "कृपया आज ही भुगतान की तारीख बताएं.\n\n"
            "सादर,\n{org_name}\n{org_contact}"
        ),
        "reminder_final_notice": (
            "विषय: भुगतान हेतु अंतिम अनुरोध — चालान {invoice_no} ({amount})\n\n"
            "आदरणीय {contact},\n\n"
            "चालान {invoice_no}, दिनांक {issue_date}, राशि {amount}, देय तिथि {due_date} थी और "
            "{days_overdue} दिन बाद भी अवैतनिक है. शेष राशि {outstanding}.\n\n"
            "हमने कई बार लिखा है. यह अंतिम अनुरोध है; इसके बाद हम उपलब्ध वसूली विकल्पों पर विचार करेंगे, "
            "जिनमें लागू होने पर MSME समाधान / MSEFC मार्ग शामिल हो सकता है.\n\n"
            "निपटान के लिए: {pay_link}\n"
            "आपके रिकॉर्ड के लिए खाता विवरण और चालान की प्रतियाँ संलग्न हैं.\n\n"
            "यदि भुगतान हो चुका है तो UTR साझा करें, हम आज ही बंद कर देंगे.\n\n"
            "सादर,\n{org_name}\n{org_contact}"
        ),
    },
}


def render(
    template: str,
    *,
    locale: str = "en",
    context: dict[str, str],
) -> str:
    table = TEMPLATES.get(locale) or TEMPLATES["en"]
    body = table.get(template) or TEMPLATES["en"].get(template, "")
    safe = {k: ("" if v is None else str(v)) for k, v in context.items()}
    try:
        return body.format(**safe)
    except KeyError as exc:  # a missing placeholder must never crash a send
        return body + f"\n[template missing {exc}]"


def context_for(
    *,
    invoice: Invoice,
    customer: Customer,
    org: Organization,
    pay_link: str,
    plan_link: str,
    as_of: dt.date,
    locale: str = "en",
) -> dict[str, str]:
    outstanding = outstanding_of(invoice)
    days_overdue = max(0, (as_of - invoice.due_date).days)
    description_line = ""
    if invoice.description:
        label = "विवरण" if locale == "hi" else "Details"
        description_line = f"\n{label}: {invoice.description}\n"
    org_contact = " | ".join(p for p in (org.phone_e164, org.billing_email) if p)
    return {
        "contact": customer.contact_name or customer.name,
        "customer_name": customer.name,
        "org_name": org.name,
        "org_contact": org_contact,
        "invoice_no": invoice.invoice_number,
        "amount": format_paise(int(invoice.total_paise)),
        "amount_plain": format_paise_plain(int(invoice.total_paise)),
        "outstanding": format_paise(outstanding),
        "outstanding_plain": format_paise_plain(outstanding),
        "due_date": _fmt_date(invoice.due_date, locale),
        "issue_date": _fmt_date(invoice.issue_date, locale),
        "days_overdue": str(days_overdue),
        "description_line": description_line,
        "pay_link": pay_link,
        "plan_link": plan_link,
    }


_MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hi": ["जन", "फ़र", "मार्च", "अप्रैल", "मई", "जून", "जुल", "अग", "सित", "अक्ट", "नव", "दिस"],
}


def _fmt_date(d: dt.date, locale: str = "en") -> str:
    months = _MONTHS.get(locale, _MONTHS["en"])
    return f"{d.day:02d} {months[d.month - 1]} {d.year}"


__all__ = [
    "LADDER",
    "TEMPLATES",
    "TEMPLATE_BY_STAGE",
    "Decimal",
    "LadderStep",
    "cancel_pending",
    "context_for",
    "due_reminders",
    "format_paise",
    "is_step_sendable",
    "plan_for_invoice",
    "render",
    "schedule_datetime",
    "steps_for",
    "template_for_stage",
]
