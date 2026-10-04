"""Messaging adapters: WhatsApp, SMS, email, and a console sink.

India-specific constraints baked in as design rules:
* WhatsApp utility messages require a **customer opt-in** — the sender refuses
  to send to a customer who has not opted in, unless the adapter is explicitly
  told this is a service-window reply. See ``research/05-dpdp-messaging-hosting.md``.
* SMS requires **DLT** registration (entity + header + template). The SMS
  adapter refuses to run unless the DLT identifiers are configured, so we can
  never accidentally send an unregistered commercial SMS.
* The console adapter is the default everywhere except production, so no real
  message is ever sent during development or tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class Message:
    to: str
    body: str
    channel: str = "whatsapp"
    template: str | None = None
    locale: str = "en"
    # WhatsApp template sends need these; utility templates are the only kind we
    # use for transactional reminders (no marketing category).
    template_variables: dict[str, str] | None = None
    subject: str | None = None
    related_type: str | None = None
    related_id: str | None = None


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class MessagingAdapter(Protocol):
    name: str

    def send(self, message: Message, *, opt_in: bool = False) -> SendResult: ...


class ConsoleAdapter:
    """Writes messages to the log and stores them. Never touches a network."""

    name = "console"

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message, *, opt_in: bool = False) -> SendResult:
        self.sent.append(message)
        logger.info("[console-message] channel=%s to=%s", message.channel, _mask(message.to))
        return SendResult(ok=True, provider_message_id=f"console-{len(self.sent)}")


def _mask(address: str | None, keep: int = 3) -> str:
    if not address:
        return ""
    if len(address) <= keep:
        return "***"
    return "***" + address[-keep:]


class WhatsAppAdapter:
    """WhatsApp Business Platform (Cloud API).

    We send **utility** templates for reminders. Marketing templates are
    deliberately not implemented: a dunning reminder is transactional, and
    sending it as marketing would be both wrong and more expensive.
    """

    name = "whatsapp"

    def __init__(self, token: str, phone_number_id: str, api_url: str | None = None) -> None:
        self.token = token
        self.phone_number_id = phone_number_id
        self.api_url = (api_url or f"https://graph.facebook.com/v21.0/{phone_number_id}/messages").rstrip("/")

    def send(self, message: Message, *, opt_in: bool = False) -> SendResult:
        if not self.token or not self.phone_number_id:
            return SendResult(ok=False, error="whatsapp credentials not configured")
        if not opt_in:
            # Hard stop: no opt-in, no automated message. The org can still
            # message the customer manually from their own phone.
            return SendResult(ok=False, error="customer has not opted in to WhatsApp messages")
        payload: dict = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": _to_e164_digits(message.to),
            "type": "text",
            "text": {"preview_url": False, "body": message.body[:4096]},
        }
        if message.template:
            payload = {
                "messaging_product": "whatsapp",
                "to": _to_e164_digits(message.to),
                "type": "template",
                "template": {
                    "name": message.template,
                    "language": {"code": "en" if message.locale == "en" else "hi"},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": v}
                                for v in (message.template_variables or {}).values()
                            ],
                        }
                    ],
                },
            }
        try:
            resp = httpx.post(
                self.api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"transport error: {type(exc).__name__}")
        if resp.status_code >= 400:
            return SendResult(ok=False, error=f"HTTP {resp.status_code}")
        try:
            data = resp.json()
            mid = (((data.get("messages") or [{}])[0]).get("id")) if isinstance(data, dict) else None
        except ValueError:
            mid = None
        return SendResult(ok=True, provider_message_id=str(mid) if mid else None)


def _to_e164_digits(value: str) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) == 10:
        return "91" + digits
    return digits


class SmsAdapter:
    """Transactional SMS over an Indian DLT-registered sender.

    Refuses to send unless the DLT entity id, sender header and template id are
    all configured — TRAI requires commercial SMS to be registered on DLT, and
    an unregistered send would simply be dropped (or worse, get the sender
    blacklisted).
    """

    name = "sms_dlt"

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        sender_id: str,
        dlt_entity_id: str,
        dlt_template_id: str,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.sender_id = sender_id
        self.dlt_entity_id = dlt_entity_id
        self.dlt_template_id = dlt_template_id

    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key and self.sender_id and self.dlt_entity_id and self.dlt_template_id)

    def send(self, message: Message, *, opt_in: bool = False) -> SendResult:
        if not self.is_configured():
            return SendResult(
                ok=False,
                error=(
                    "SMS not configured: DLT entity id, sender header and template id are required "
                    "before any commercial SMS can be sent in India (see docs/HUMAN_TODO.md)."
                ),
            )
        payload = {
            "sender": self.sender_id,
            "to": _to_e164_digits(message.to),
            "message": message.body[:1000],
            "entityid": self.dlt_entity_id,
            "templateid": self.dlt_template_id,
        }
        try:
            resp = httpx.post(
                self.api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"transport error: {type(exc).__name__}")
        if resp.status_code >= 400:
            return SendResult(ok=False, error=f"HTTP {resp.status_code}")
        return SendResult(ok=True)


class EmailAdapter:
    """Transactional email over SMTP — no proprietary dependency needed."""

    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender

    def send(self, message: Message, *, opt_in: bool = False) -> SendResult:
        if not self.host or not self.sender:
            return SendResult(ok=False, error="email transport not configured")
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = message.to
        msg["Subject"] = message.subject or "Payment reminder"
        msg.set_content(message.body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
                smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except Exception as exc:
            return SendResult(ok=False, error=f"smtp error: {type(exc).__name__}")
        return SendResult(ok=True)


def build_messaging(settings: Settings) -> MessagingAdapter:
    provider = (settings.messaging_provider or "console").lower()
    if provider == "whatsapp":
        return WhatsAppAdapter(settings.whatsapp_token, settings.whatsapp_phone_number_id, settings.whatsapp_api_url)
    if provider == "sms_dlt":
        return SmsAdapter(
            api_url=settings.sms_api_url,
            api_key=settings.sms_api_key,
            sender_id=settings.sms_sender_id,
            dlt_entity_id=settings.sms_dlt_entity_id,
            dlt_template_id=settings.sms_dlt_template_id,
        )
    if provider == "email":
        return EmailAdapter(
            settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_from
        )
    return ConsoleAdapter()


def channel_adapter(settings: Settings, channel: str) -> MessagingAdapter:
    """Route a channel to its adapter, regardless of the default provider.

    This is what makes the reminder ladder able to mix WhatsApp and SMS: each
    step asks for its channel and gets the right adapter.
    """
    channel = (channel or "whatsapp").lower()
    if channel == "sms":
        sms = SmsAdapter(
            api_url=settings.sms_api_url,
            api_key=settings.sms_api_key,
            sender_id=settings.sms_sender_id,
            dlt_entity_id=settings.sms_dlt_entity_id,
            dlt_template_id=settings.sms_dlt_template_id,
        )
        if sms.is_configured():
            return sms
        # Fall back to console when SMS is not configured yet, so development
        # and tests still exercise the ladder end to end.
        return ConsoleAdapter()
    if channel == "email":
        email = EmailAdapter(
            settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_from
        )
        if settings.smtp_host:
            return email
        return ConsoleAdapter()
    return build_messaging(settings)


__all__ = [
    "ConsoleAdapter",
    "EmailAdapter",
    "Message",
    "MessagingAdapter",
    "SendResult",
    "SmsAdapter",
    "WhatsAppAdapter",
    "build_messaging",
    "channel_adapter",
]
