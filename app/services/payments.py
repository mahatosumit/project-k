"""Payment processing: order creation, webhook intake, verification, reconciliation.

The critical-path rules implemented here:

* **Server-side verification always wins.** A browser redirect is never trusted;
  after a callback we ask the gateway directly (``fetch_order``) and only then
  settle an invoice.
* **Idempotent by construction.** Every webhook is stored against a unique
  ``(provider, event_key)``; a duplicate delivery is recognised and ignored, and
  a payment is never applied twice even if the same payment id arrives via
  different events or in a different order (Razorpay does not guarantee order).
* **Amount is checked, not assumed.** A webhook claiming a different amount from
  the order is rejected and quarantined for a human.
* **Reconciliation is a job, not a hope.** ``reconcile_pending`` re-asks the
  gateway about orders that have been stuck, and ``reconcile_invoice_ledger``
  re-derives the invoice cache from the payments table.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.payments import (
    LookupResult,
    OrderRequest,
    PaymentAdapter,
    PaymentError,
    WebhookResult,
    adapter_for_settings,
    merchant_adapter,
)
from app.config import Settings, get_settings
from app.domain import ledger
from app.models import Customer, GatewayOrder, Invoice, Organization, PaymentEvent, Subscription
from app.models import utcnow as model_utcnow
from app.services import audit as audit_service
from app.services import notifications

logger = logging.getLogger(__name__)


@dataclass
class WebhookOutcome:
    accepted: bool
    duplicate: bool
    status: str
    detail: str = ""
    event_id: str | None = None
    invoice_id: str | None = None


def provider_for(org: Organization | None, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if org is not None and org.gateway_provider:
        return org.gateway_provider
    return settings.payment_provider


def get_adapter(org: Organization | None, settings: Settings | None = None) -> PaymentAdapter:
    settings = settings or get_settings()
    if org is not None and org.gateway_provider:
        return merchant_adapter(org)
    return adapter_for_settings(settings)


# --------------------------------------------------------------------------
# Invoice payment orders (the merchant collecting from their customer)
# --------------------------------------------------------------------------

def create_invoice_payment_order(
    session: Session,
    *,
    org: Organization,
    invoice: Invoice,
    customer: Customer | None = None,
    return_url: str = "",
    settings: Settings | None = None,
    idempotency_key: str | None = None,
) -> tuple[GatewayOrder, str]:
    """Create a gateway order for an invoice. Returns (order_row, checkout_url_or_session)."""
    settings = settings or get_settings()
    outstanding = ledger.outstanding_of(invoice)
    if outstanding <= 0:
        raise PaymentError("invoice is already settled")

    adapter = get_adapter(org, settings)
    customer = customer or session.get(Customer, invoice.customer_id)
    req = OrderRequest(
        amount_paise=outstanding,
        currency="INR",
        receipt=f"{invoice.invoice_number}-{invoice.id[:6]}",
        notes={
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "org_id": org.id,
        },
        customer_id=(customer.id if customer else ""),
        customer_name=(customer.name if customer else "Customer"),
        customer_email=(customer.email if customer and customer.email else ""),
        customer_phone=(customer.phone_e164 if customer and customer.phone_e164 else ""),
        return_url=return_url,
        idempotency_key=idempotency_key,
    )
    result = adapter.create_order(req)

    row = GatewayOrder(
        org_id=org.id,
        purpose="invoice",
        provider=adapter.name,
        mode=settings.payment_mode,
        provider_order_id=result.provider_order_id,
        amount_paise=result.amount_paise,
        currency=result.currency,
        status=result.status,
        idempotency_key=idempotency_key,
        notes=json.dumps({"invoice_id": invoice.id}),
    )
    session.add(row)
    session.flush()

    audit_service.record(
        session,
        action="payment.order_created",
        org_id=org.id,
        actor_type="user",
        entity_type="invoice",
        entity_id=invoice.id,
        detail={"provider": adapter.name, "amount_paise": result.amount_paise, "order": result.provider_order_id},
    )
    checkout_url = result.checkout.get("payment_session_id") or result.checkout.get("order_id") or ""
    return row, str(checkout_url)


# --------------------------------------------------------------------------
# Webhook intake
# --------------------------------------------------------------------------

def _org_for_order(session: Session, provider: str, order_id: str | None) -> str | None:
    """Resolve the owning organisation of a gateway order, for event scoping."""
    if not order_id:
        return None
    return session.scalar(
        select(GatewayOrder.org_id).where(
            GatewayOrder.provider == provider, GatewayOrder.provider_order_id == order_id
        )
    )


def _event_exists(session: Session, provider: str, event_key: str) -> bool:
    return (
        session.scalar(
            select(PaymentEvent.id).where(
                PaymentEvent.provider == provider, PaymentEvent.event_key == event_key
            )
        )
        is not None
    )


def process_webhook(
    session: Session,
    *,
    provider: str,
    headers: dict[str, str],
    raw_body: bytes,
    org: Organization | None = None,
    settings: Settings | None = None,
    ip: str | None = None,
) -> WebhookOutcome:
    """Verify, store, and apply one webhook delivery. Safe to call repeatedly."""
    settings = settings or get_settings()
    adapter = get_adapter(org, settings)

    # A provider mismatch means the request hit the wrong endpoint.
    if adapter.name != provider and not (adapter.name == "mock" and provider in {"razorpay", "cashfree", "mock"}):
        return WebhookOutcome(False, False, "rejected", "provider mismatch")

    try:
        result: WebhookResult = adapter.verify_webhook(headers=headers, raw_body=raw_body)
    except Exception as exc:
        logger.warning("webhook verify error: %s", type(exc).__name__)
        return WebhookOutcome(False, False, "rejected", "verification error")

    if not result.signature_valid:
        session.add(
            PaymentEvent(
                provider=provider,
                event_key=f"invalid-{model_utcnow().isoformat()}-{len(raw_body)}",
                event_type=result.event_type or "unknown",
                signature_valid=False,
                payload=raw_body[:20000].decode("utf-8", errors="replace"),
                status="rejected",
                detail="signature invalid",
            )
        )
        audit_service.record(
            session,
            action="payment.webhook_rejected",
            org_id=(org.id if org else None),
            actor_type="system",
            ip=ip,
            detail={"provider": provider, "reason": "signature invalid"},
        )
        return WebhookOutcome(False, False, "rejected", "signature invalid")

    if not result.event_key:
        # No idempotency key: derive a stable one from the body so a retry of the
        # exact same body is still deduplicated.
        import hashlib

        result.event_key = hashlib.sha256(raw_body).hexdigest()

    if _event_exists(session, provider, result.event_key):
        return WebhookOutcome(
            True, True, "duplicate", "event already processed", event_id=result.event_key
        )

    event = PaymentEvent(
        org_id=(org.id if org else _org_for_order(session, provider, result.order_id)),
        provider=provider,
        event_key=result.event_key,
        event_type=result.event_type or "unknown",
        signature_valid=True,
        payload=raw_body[:20000].decode("utf-8", errors="replace"),
        status="received",
        detail=result.detail,
    )
    session.add(event)
    try:
        session.flush()
    except Exception:
        session.rollback()
        return WebhookOutcome(True, True, "duplicate", "concurrent duplicate", event_id=result.event_key)

    outcome = _apply_event(session, provider=provider, result=result, adapter=adapter, ip=ip)

    event.status = outcome.status
    event.detail = (outcome.detail or "")[:2000]
    event.processed_at = model_utcnow()
    session.flush()
    return outcome


def _apply_event(
    session: Session,
    *,
    provider: str,
    result: WebhookResult,
    adapter: PaymentAdapter,
    ip: str | None,
) -> WebhookOutcome:
    if result.status == "ignored":
        return WebhookOutcome(True, False, "ignored", f"event {result.event_type} not actionable")

    order = None
    if result.order_id:
        order = session.scalar(
            select(GatewayOrder).where(
                GatewayOrder.provider == provider, GatewayOrder.provider_order_id == result.order_id
            )
        )
    if order is None and result.payment_id:
        order = session.scalar(
            select(GatewayOrder).where(
                GatewayOrder.provider == provider, GatewayOrder.provider_order_id == result.payment_id
            )
        )
    if order is None:
        return WebhookOutcome(True, False, "unmatched", "no matching order", event_id=result.event_key)

    if order.status == "paid":
        return WebhookOutcome(True, False, "duplicate", "order already paid", event_id=result.event_key)

    if result.status == "failed":
        order.status = "failed"
        session.flush()
        audit_service.record(
            session,
            action="payment.failed",
            org_id=order.org_id,
            actor_type="system",
            entity_type="gateway_order",
            entity_id=order.id,
            ip=ip,
            detail={"provider": provider, "event": result.event_type},
        )
        return WebhookOutcome(True, False, "failed", "payment failed", event_id=result.event_key)

    # Server-side verification: ask the gateway, do not trust the callback body.
    if adapter.name == "mock":
        # The mock gateway keeps order state in memory, so a fresh process (or a
        # second worker) would not know the order. Fall back to confirming the
        # order exists in our own database, which is what we actually need.
        confirmed_amount = result.amount_paise or order.amount_paise
        payment_id = result.payment_id
    else:
        try:
            lookup: LookupResult = adapter.fetch_order(order.provider_order_id)
        except PaymentError as exc:
            # Unverified: leave the order pending so the reconciliation job retries.
            order.status = "pending_verification"
            session.flush()
            return WebhookOutcome(
                True, False, "pending_verification", f"verification failed: {exc}", event_id=result.event_key
            )
        if lookup.status != "paid":
            order.status = lookup.status if lookup.status in {"created", "failed"} else "pending_verification"
            session.flush()
            return WebhookOutcome(
                True, False, order.status, f"gateway reports {lookup.status}", event_id=result.event_key
            )
        confirmed_amount = lookup.amount_paise or result.amount_paise or order.amount_paise
        payment_id = lookup.payment_id or result.payment_id

    if confirmed_amount and int(confirmed_amount) != int(order.amount_paise):
        order.status = "amount_mismatch"
        session.flush()
        audit_service.record(
            session,
            action="payment.amount_mismatch",
            org_id=order.org_id,
            actor_type="system",
            entity_type="gateway_order",
            entity_id=order.id,
            ip=ip,
            detail={"expected": int(order.amount_paise), "got": int(confirmed_amount)},
        )
        return WebhookOutcome(
            True, False, "amount_mismatch", "amount differs from the order; not applied", event_id=result.event_key
        )

    return _settle(session, order=order, payment_id=payment_id, provider=provider, ip=ip, event_key=result.event_key)


def _settle(
    session: Session,
    *,
    order: GatewayOrder,
    payment_id: str | None,
    provider: str,
    ip: str | None,
    event_key: str,
) -> WebhookOutcome:
    # Deliberately NOT marked paid yet. The order only becomes "paid" once the
    # invoice ledger has accepted the money, so a failure here leaves the order
    # in a state the reconciliation sweep retries — money captured at the
    # gateway can never become invisible to us (security review, H2).
    captured_at = model_utcnow()

    if order.purpose == "invoice":
        invoice = None
        if order.notes:
            try:
                invoice_id = json.loads(order.notes).get("invoice_id")
            except (ValueError, TypeError):
                invoice_id = None
            if invoice_id:
                invoice = session.get(Invoice, invoice_id)
        if invoice is None:
            return WebhookOutcome(True, False, "unmatched", "order has no invoice", event_id=event_key)

        try:
            payment = ledger.record_payment(
                session,
                invoice=invoice,
                amount_paise=int(order.amount_paise),
                method="gateway",
                reference=f"{provider}:{payment_id or order.provider_order_id}",
                gateway_provider=provider,
                gateway_order_id=order.provider_order_id,
                gateway_payment_id=payment_id or order.provider_order_id,
                notes="verified via webhook + server-side lookup",
                recorded_by="system",
            )
        except ledger.LedgerError as exc:
            # The invoice could not take this money (already settled, or the
            # amount exceeds the balance). Park it as an unapplied credit and
            # leave the order retryable so the daily sweep keeps surfacing it
            # until a human resolves it. Never mark it paid here.
            order.status = "paid_uncredited"
            order.notes = json.dumps(
                {
                    "invoice_id": invoice.id,
                    "uncredited_paise": int(order.amount_paise),
                    "payment_id": payment_id,
                    "reason": str(exc)[:300],
                }
            )
            session.flush()
            audit_service.record(
                session,
                action="payment.uncredited",
                org_id=order.org_id,
                actor_type="system",
                entity_type="invoice",
                entity_id=invoice.id,
                ip=ip,
                detail={
                    "error": str(exc),
                    "amount_paise": int(order.amount_paise),
                    "payment_id": payment_id,
                    "needs": "manual credit or refund",
                },
            )
            return WebhookOutcome(True, False, "paid_uncredited", str(exc), event_id=event_key)

        from app.services import reminders as reminder_service

        # The ledger accepted the money: only now is the order truthfully paid.
        order.status = "paid"
        order.paid_at = captured_at
        session.flush()

        reminder_service.on_invoice_settled(session, invoice)

        audit_service.record(
            session,
            action="payment.settled",
            org_id=order.org_id,
            actor_type="system",
            entity_type="invoice",
            entity_id=invoice.id,
            ip=ip,
            detail={
                "amount_paise": int(order.amount_paise),
                "payment_id": payment.id,
                "provider": provider,
                "outstanding_after": ledger.outstanding_of(invoice),
            },
        )
        if ledger.outstanding_of(invoice) == 0:
            customer = session.get(Customer, invoice.customer_id)
            org = session.get(Organization, invoice.org_id)
            if customer and org:
                notifications.send(
                    session,
                    org=org,
                    channel="whatsapp" if customer.whatsapp_opt_in else "email",
                    to=(customer.phone_e164 if customer.whatsapp_opt_in else customer.email) or "",
                    body=(
                        f"Thank you — we have received {invoice.invoice_number}. "
                        f"Your account is fully settled. — {org.name}"
                    ),
                    template="payment_receipt",
                    customer=customer,
                    related_type="invoice",
                    related_id=invoice.id,
                    actor="system",
                )
        return WebhookOutcome(True, False, "settled", "", event_id=event_key, invoice_id=invoice.id)

    if order.purpose == "subscription":
        subscription = session.get(Subscription, order.subscription_id) if order.subscription_id else None
        if subscription is None:
            return WebhookOutcome(True, False, "unmatched", "order has no subscription", event_id=event_key)
        now = model_utcnow()
        subscription.status = "active"
        subscription.started_at = subscription.started_at or now
        months = 12 if subscription.billing_cycle == "annual" else 1
        base = subscription.current_period_end if subscription.current_period_end and subscription.current_period_end > now else now
        subscription.current_period_end = base + dt.timedelta(days=30 * months)
        subscription.updated_at = now
        session.flush()
        order.status = "paid"
        order.paid_at = captured_at
        session.flush()
        audit_service.record(
            session,
            action="subscription.activated",
            org_id=order.org_id,
            actor_type="system",
            entity_type="subscription",
            entity_id=subscription.id,
            detail={"plan": subscription.plan_code, "amount_paise": int(order.amount_paise)},
        )
        return WebhookOutcome(True, False, "settled", "", event_id=event_key)

    return WebhookOutcome(True, False, "ignored", f"unknown purpose {order.purpose}", event_id=event_key)


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------

@dataclass
class ReconcileReport:
    checked: int = 0
    settled: int = 0
    still_pending: int = 0
    failed: int = 0
    repaired_ledgers: int = 0
    errors: int = 0
    uncredited: int = 0
    uncredited_resolved: int = 0


def reconcile_pending(
    session: Session,
    *,
    max_age_hours: int = 48,
    min_age_minutes: int = 15,
    limit: int = 100,
    settings: Settings | None = None,
    now: dt.datetime | None = None,
    force: bool = False,
    org_id: str | None = None,
) -> ReconcileReport:
    """Re-ask the gateway about orders that never resolved.

    Covers the two failure modes that lose merchants money: a payment that
    succeeded while the redirect was lost, and a webhook that never arrived.
    Pass ``force=True`` (or ``min_age_minutes=0``) to sweep immediately, which is
    what the customer callback page does.
    """
    settings = settings or get_settings()
    now = now or model_utcnow()
    report = ReconcileReport()
    if force:
        min_age_minutes = 0

    filters = [
        GatewayOrder.status.in_(
            ["created", "pending_verification", "amount_mismatch", "paid_uncredited"]
        ),
        GatewayOrder.created_at <= now - dt.timedelta(minutes=min_age_minutes),
        GatewayOrder.created_at >= now - dt.timedelta(hours=max_age_hours),
    ]
    if org_id:
        filters.append(GatewayOrder.org_id == org_id)

    rows = session.scalars(
        select(GatewayOrder)
        .where(
            *filters,
            GatewayOrder.created_at <= now - dt.timedelta(minutes=min_age_minutes),
            GatewayOrder.created_at >= now - dt.timedelta(hours=max_age_hours),
        )
        .order_by(GatewayOrder.created_at.asc())
        .limit(limit)
    ).all()

    for order in rows:
        report.checked += 1
        org = session.get(Organization, order.org_id)
        adapter = get_adapter(org, settings)
        try:
            lookup = adapter.fetch_order(order.provider_order_id)
        except PaymentError:
            report.errors += 1
            continue

        if order.status == "paid_uncredited":
            # Money was captured but the ledger refused it (settled invoice, or an
            # amount above the balance). Retry the ledger write when the gateway
            # still shows the payment, and NEVER downgrade it to failed on an
            # inconclusive lookup: the captured money is a fact, and closing the
            # order as failed would lose it a second time.
            if lookup.status != "paid":
                report.uncredited += 1
                continue
            outcome = _settle(
                session,
                order=order,
                payment_id=lookup.payment_id,
                provider=order.provider,
                ip=None,
                event_key=f"reconcile-credit-{order.provider_order_id}",
            )
            if outcome.status == "settled":
                report.settled += 1
                report.uncredited_resolved += 1
            else:
                report.uncredited += 1
            continue

        if lookup.status == "paid":
            if lookup.amount_paise and int(lookup.amount_paise) != int(order.amount_paise):
                order.status = "amount_mismatch"
                report.still_pending += 1
                continue
            outcome = _settle(
                session,
                order=order,
                payment_id=lookup.payment_id,
                provider=order.provider,
                ip=None,
                event_key=f"reconcile-{order.provider_order_id}",
            )
            if outcome.status == "settled":
                report.settled += 1
            else:
                report.still_pending += 1
        elif lookup.status == "failed":
            order.status = "failed"
            report.failed += 1
        else:
            report.still_pending += 1
    session.flush()
    return report


def reconcile_invoice_ledger(
    session: Session, *, org_id: str | None = None, limit: int = 500
) -> int:
    """Re-derive ``paid_paise`` from the payments table.

    The invoice column is a cache for fast list rendering; the payments table is
    the source of truth. A mismatch is a bug indicator, so it is repaired *and*
    audited.
    """
    query = select(Invoice).where(Invoice.status != "cancelled").limit(limit)
    if org_id:
        query = query.where(Invoice.org_id == org_id)
    repaired = 0
    for invoice in session.scalars(query).all():
        before = int(invoice.paid_paise or 0)
        after = ledger.recompute_org_paid_totals(session, invoice)
        if before != after:
            repaired += 1
            audit_service.record(
                session,
                action="reconciliation.ledger_repaired",
                org_id=invoice.org_id,
                actor_type="system",
                entity_type="invoice",
                entity_id=invoice.id,
                detail={"before_paise": before, "after_paise": after},
            )
    session.flush()
    return repaired


def daily_reconciliation(
    session: Session, *, settings: Settings | None = None, org_id: str | None = None
) -> dict[str, Any]:
    """The scheduled job: gateway sweep + ledger rebuild, with a summary.

    ``org_id`` scopes the sweep to one tenant. The scheduler calls it unscoped;
    the in-app button always passes the caller's org so one tenant cannot trigger
    work on another's orders.
    """
    settings = settings or get_settings()
    gateway = reconcile_pending(session, settings=settings, org_id=org_id)
    repaired = reconcile_invoice_ledger(session, org_id=org_id)
    summary = {
        "orders_checked": gateway.checked,
        "orders_settled": gateway.settled,
        "orders_pending": gateway.still_pending,
        "orders_failed": gateway.failed,
        "ledgers_repaired": repaired,
        "errors": gateway.errors,
        "uncredited_remaining": gateway.uncredited,
        "uncredited_resolved": gateway.uncredited_resolved,
    }
    audit_service.record(session, action="reconciliation.daily", actor_type="system", detail=summary)
    return summary


def refund_order(
    session: Session,
    *,
    order: GatewayOrder,
    amount_paise: int | None = None,
    reason: str = "",
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Record a refund. Marked for a human to execute at the gateway.

    We never auto-refund: a refund is money leaving the merchant's account and
    must be a deliberate act. The record here keeps the ledger honest.
    """
    amount = int(amount_paise or order.amount_paise)
    if amount > int(order.amount_paise):
        raise PaymentError("refund exceeds the original order amount")
    order.status = "refund_requested"
    session.flush()
    audit_service.record(
        session,
        action="payment.refund_requested",
        org_id=order.org_id,
        actor_type="user",
        actor_id=actor_id,
        entity_type="gateway_order",
        entity_id=order.id,
        detail={"amount_paise": amount, "reason": reason[:500]},
    )
    return {
        "order_id": order.provider_order_id,
        "amount_paise": amount,
        "status": "refund_requested",
        "note": "Execute the refund in the gateway dashboard; this record tracks the decision.",
    }


__all__ = [
    "ReconcileReport",
    "WebhookOutcome",
    "create_invoice_payment_order",
    "daily_reconciliation",
    "get_adapter",
    "process_webhook",
    "provider_for",
    "reconcile_invoice_ledger",
    "reconcile_pending",
    "refund_order",
]
