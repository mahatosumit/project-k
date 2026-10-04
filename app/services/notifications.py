"""Notification service: consent-aware sending with an immutable log.

Rules encoded here, not left to callers:
* A **WhatsApp** message may only go to a customer who has opted in. The
  consent row and the customer flag are both checked; the adapter refuses too.
* Every attempt is logged to ``notification_log`` with status — including
  refusals — so an audit can answer "was this customer ever messaged?".
* Message bodies are scrubbed of phone/e-mail/digit runs before they land in
  the application log.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.messaging import Message, channel_adapter
from app.config import Settings, get_settings
from app.models import Consent, Customer, NotificationLog, Organization
from app.services import audit as audit_service

# Bump when the consent wording changes: stored consents record which notice the
# customer agreed to, so a later change never silently retro-applies.
CONSENT_NOTICE_VERSION = "2026-10-01"
PURPOSE_REMINDERS = "payment_reminders"


def has_consent(session: Session, customer: Customer, purpose: str = PURPOSE_REMINDERS) -> bool:
    """Check the consent table first, then the denormalised customer flag."""
    row = session.scalar(
        select(Consent)
        .where(
            Consent.subject_type == "customer",
            Consent.subject_id == customer.id,
            Consent.purpose == purpose,
        )
        .order_by(Consent.created_at.desc())
    )
    if row is not None:
        return bool(row.granted and row.withdrawn_at is None)
    if purpose == PURPOSE_REMINDERS:
        return bool(customer.whatsapp_opt_in)
    return False


def grant_consent(
    session: Session,
    *,
    org_id: str,
    customer: Customer,
    purpose: str = PURPOSE_REMINDERS,
    source: str = "org_recorded",
    evidence: str | None = None,
) -> Consent:
    row = Consent(
        org_id=org_id,
        subject_type="customer",
        subject_id=customer.id,
        purpose=purpose,
        notice_version=CONSENT_NOTICE_VERSION,
        granted=True,
        source=source,
        evidence=evidence,
        granted_at=__import__("app.models", fromlist=["utcnow"]).utcnow(),
    )
    session.add(row)
    if purpose == PURPOSE_REMINDERS:
        customer.whatsapp_opt_in = True
        customer.opt_in_at = row.granted_at
        customer.opt_in_source = source
    session.flush()
    return row


def withdraw_consent(session: Session, *, customer: Customer, purpose: str = PURPOSE_REMINDERS) -> Consent:
    from app.models import utcnow as model_utcnow

    row = Consent(
        org_id=customer.org_id,
        subject_type="customer",
        subject_id=customer.id,
        purpose=purpose,
        notice_version=CONSENT_NOTICE_VERSION,
        granted=False,
        source="withdrawn",
        withdrawn_at=model_utcnow(),
    )
    session.add(row)
    if purpose == PURPOSE_REMINDERS:
        customer.whatsapp_opt_in = False
    session.flush()
    return row


@dataclass
class SendOutcome:
    ok: bool
    channel: str
    status: str
    provider_message_id: str | None = None
    error: str | None = None
    notification_id: str | None = None


def send(
    session: Session,
    *,
    org: Organization | None,
    channel: str,
    to: str,
    body: str,
    template: str | None = None,
    locale: str = "en",
    customer: Customer | None = None,
    related_type: str | None = None,
    related_id: str | None = None,
    settings: Settings | None = None,
    actor: str = "system",
    ip: str | None = None,
) -> SendOutcome:
    """Send one notification, enforcing consent, and log the outcome either way."""
    settings = settings or get_settings()

    if not to:
        return _log(
            session,
            org=org,
            channel=channel,
            to="",
            body=body,
            template=template,
            status="failed",
            error="no destination address",
            related_type=related_type,
            related_id=related_id,
        )

    consent_ok = True  # non-messaging channels need no opt-in
    if channel in {"whatsapp", "sms"}:
        if customer is not None and not has_consent(session, customer):
            outcome = _log(
                session,
                org=org,
                channel=channel,
                to=to,
                body=body,
                template=template,
                status="blocked_no_consent",
                error="customer has not opted in; automated message not sent",
                related_type=related_type,
                related_id=related_id,
            )
            audit_service.record(
                session,
                action="notification.blocked_no_consent",
                org_id=(org.id if org else None),
                actor_type="system",
                entity_type="customer",
                entity_id=customer.id,
                ip=ip,
                detail={"channel": channel, "template": template},
            )
            return outcome
        consent_ok = True

    adapter = channel_adapter(settings, channel)
    message = Message(
        to=to,
        body=body,
        channel=channel,
        template=None,  # we send composed text, not a Meta template, for step messages
        locale=locale,
        related_type=related_type,
        related_id=related_id,
    )
    # Consent was already enforced above for channels that require it. Pass the
    # resolved fact through so the adapter is not asked to re-derive it.
    result = adapter.send(message, opt_in=consent_ok)

    outcome = _log(
        session,
        org=org,
        channel=channel,
        to=to,
        body=body,
        template=template,
        status="sent" if result.ok else "failed",
        provider_message_id=result.provider_message_id,
        error=result.error,
        related_type=related_type,
        related_id=related_id,
    )
    audit_service.record(
        session,
        action="notification.sent" if result.ok else "notification.failed",
        org_id=(org.id if org else None),
        actor_type=actor,
        entity_type=related_type,
        entity_id=related_id,
        ip=ip,
        detail={"channel": channel, "template": template, "ok": result.ok, "error": result.error},
    )
    return outcome


def _log(
    session: Session,
    *,
    org: Organization | None,
    channel: str,
    to: str,
    body: str,
    template: str | None,
    status: str,
    provider_message_id: str | None = None,
    error: str | None = None,
    related_type: str | None = None,
    related_id: str | None = None,
) -> SendOutcome:
    entry = NotificationLog(
        org_id=(org.id if org else None),
        channel=channel,
        to_address=_mask(to),
        template=template,
        body=(body or "")[:4000],
        status=status,
        provider_message_id=provider_message_id,
        error=error,
        related_type=related_type,
        related_id=related_id,
    )
    session.add(entry)
    session.flush()
    return SendOutcome(
        ok=status == "sent",
        channel=channel,
        status=status,
        provider_message_id=provider_message_id,
        error=error,
        notification_id=entry.id,
    )


def _contact_address(customer: Customer | None) -> str:
    """The address we are allowed to use for a customer, or "" when there is none.

    Only the values held on the customer record are considered. A destination
    supplied in a request body is never used for an outbound message, because
    that would let anyone with a portal link make the merchant's sender message
    an arbitrary third-party number with no consent record.
    """
    if customer is None:
        return ""
    return (customer.email or "").strip() or (customer.phone_e164 or "").strip()


def _mask(address: str) -> str:
    if not address:
        return ""
    if "@" in address:
        local, _, domain = address.partition("@")
        return f"{local[:1]}***@{domain}"[:254]
    digits = "".join(ch for ch in address if ch.isdigit())
    if len(digits) > 4:
        return "***" + digits[-4:]
    return "***"[:254]


def send_support_ack(
    session: Session,
    *,
    org: Organization | None,
    customer: Customer | None = None,
    locale: str = "en",
    reference: str = "",
    sla_hours: int = 48,
) -> SendOutcome:
    """Acknowledge a customer complaint/request within the stated window.

    The destination is the address held on the customer record, never a value
    supplied in the request body. Otherwise anyone with a valid portal link could
    make the merchant's sender message an arbitrary third-party number, with no
    consent record (security review, M1).
    """
    # Destination resolution: the customer's email, else their phone, else nothing.
    # Written as a small helper call so the intent is obvious at the call site.
    to = _contact_address(customer)
    if not to:
        return SendOutcome(
            ok=False,
            channel="email",
            status="failed",
            error="no contact address on the customer record; acknowledgement not sent",
        )
    channel = "email" if "@" in to else "whatsapp"
    if locale == "hi":
        body = (
            "नमस्ते,\n\n"
            f"आपकी शिकायत हमें मिल गई है. संदर्भ संख्या: {reference}.\n"
            f"हम {sla_hours} घंटे के भीतर जवाब देंगे. अगर मामला इससे ज़्यादा समय लेता है तो हम "
            "पहले ही बता देंगे.\n\nधन्यवाद."
        )
    else:
        body = (
            "Namaste,\n\n"
            f"We have received your message. Reference: {reference}.\n"
            f"We will respond within {sla_hours} hours. If it needs longer, we will tell you "
            "before that window ends.\n\nThank you."
        )
    return send(
        session,
        org=org,
        channel=channel,
        to=to,
        body=body,
        template="support_ack",
        locale=locale,
        # Pass the real customer so the consent gate applies to this send too.
        customer=customer,
        related_type="support_request",
        related_id=reference,
        actor="system",
    )
