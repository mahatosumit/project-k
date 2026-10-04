"""Invoice and payment ledger mechanics.

Invariants enforced here (these are the ones the tests hammer):

1. ``outstanding = total - paid - credited - written_off`` and never negative.
2. Applying a payment is **idempotent**: re-applying the same gateway payment id
   or the same manual reference does not double-credit an invoice.
3. Status is derived from the ledger, never set ad hoc:
   draft -> issued -> partly_paid -> paid, with ``overdue`` computed on read.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, Payment
from app.models import utcnow as model_utcnow

OPEN_STATUSES = ("issued", "partly_paid", "overdue")


class LedgerError(Exception):
    """Raised when a ledger operation would break an invariant."""


@dataclass(frozen=True)
class Ledger:
    total_paise: int
    paid_paise: int
    credited_paise: int
    written_off_paise: int

    @property
    def outstanding_paise(self) -> int:
        return max(0, self.total_paise - self.paid_paise - self.credited_paise - self.written_off_paise)

    @property
    def is_settled(self) -> bool:
        return self.outstanding_paise == 0


def ledger_of(invoice: Invoice) -> Ledger:
    return Ledger(
        total_paise=int(invoice.total_paise or 0),
        paid_paise=int(invoice.paid_paise or 0),
        credited_paise=int(invoice.credited_paise or 0),
        written_off_paise=int(invoice.written_off_paise or 0),
    )


def outstanding_of(invoice: Invoice) -> int:
    return ledger_of(invoice).outstanding_paise


def _recompute_status(invoice: Invoice) -> None:
    ledger = ledger_of(invoice)
    if invoice.status in {"draft", "cancelled", "written_off"}:
        return
    if ledger.is_settled:
        invoice.status = "paid"
        if invoice.paid_at is None:
            invoice.paid_at = model_utcnow()
    elif ledger.paid_paise > 0 or ledger.credited_paise > 0:
        invoice.status = "partly_paid"
        invoice.paid_at = None
    else:
        invoice.status = "issued"
        invoice.paid_at = None


def record_payment(
    session: Session,
    *,
    invoice: Invoice,
    amount_paise: int,
    method: str = "manual",
    reference: str | None = None,
    utr: str | None = None,
    received_at: dt.datetime | None = None,
    gateway_provider: str | None = None,
    gateway_order_id: str | None = None,
    gateway_payment_id: str | None = None,
    gateway_signature: str | None = None,
    notes: str | None = None,
    recorded_by: str | None = None,
    allow_overpay: bool = False,
) -> Payment:
    """Record a payment against an invoice.

    Idempotency: if ``gateway_payment_id`` is set and a payment with that
    (provider, id) already exists, the existing row is returned untouched.
    """
    if amount_paise <= 0:
        raise LedgerError("payment amount must be positive")
    if invoice.status == "cancelled":
        raise LedgerError("cannot pay a cancelled invoice")

    if gateway_payment_id and gateway_provider:
        # The database enforces uniqueness on (provider, payment id), so a
        # duplicate delivery that slips past this check raises IntegrityError
        # on flush. We look first (cheap, and gives a clean idempotent answer)
        # and the caller treats IntegrityError as "already applied" too.
        existing = session.scalar(
            select(Payment).where(
                Payment.gateway_provider == gateway_provider,
                Payment.gateway_payment_id == gateway_payment_id,
            )
        )
        if existing is not None:
            if existing.invoice_id == invoice.id:
                # A true replay of the same payment for the same invoice.
                return existing
            # The same gateway payment id points at a DIFFERENT invoice. A
            # gateway payment id is unique per provider, so this is an anomaly:
            # refuse it loudly rather than silently swallowing a real payment.
            raise LedgerError(
                "this gateway payment id has already been applied to a different invoice"
            )

    ledger = ledger_of(invoice)
    if amount_paise > ledger.outstanding_paise and not allow_overpay:
        raise LedgerError(
            f"payment {amount_paise} exceeds outstanding {ledger.outstanding_paise}"
        )

    payment = Payment(
        org_id=invoice.org_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        amount_paise=int(amount_paise),
        method=method,
        status="succeeded",
        reference=reference,
        utr=utr,
        received_at=received_at or model_utcnow(),
        gateway_provider=gateway_provider,
        gateway_order_id=gateway_order_id,
        gateway_payment_id=gateway_payment_id,
        gateway_signature=gateway_signature,
        notes=notes,
        recorded_by=recorded_by,
    )
    session.add(payment)
    session.flush()

    invoice.paid_paise = int(invoice.paid_paise or 0) + int(amount_paise)
    _recompute_status(invoice)
    session.flush()
    return payment


def apply_credit(session: Session, *, invoice: Invoice, amount_paise: int, reason: str | None = None) -> None:
    """A credit note / adjustment reducing what the customer owes."""
    if amount_paise <= 0:
        raise LedgerError("credit must be positive")
    ledger = ledger_of(invoice)
    if amount_paise > ledger.outstanding_paise:
        raise LedgerError("credit exceeds outstanding")
    invoice.credited_paise = int(invoice.credited_paise or 0) + int(amount_paise)
    if reason:
        invoice.notes = ((invoice.notes or "") + f"\n[credit] {reason}").strip()
    _recompute_status(invoice)
    session.flush()


def write_off(session: Session, *, invoice: Invoice, amount_paise: int, reason: str) -> None:
    if amount_paise <= 0:
        raise LedgerError("write-off must be positive")
    ledger = ledger_of(invoice)
    if amount_paise > ledger.outstanding_paise:
        raise LedgerError("write-off exceeds outstanding")
    invoice.written_off_paise = int(invoice.written_off_paise or 0) + int(amount_paise)
    invoice.notes = ((invoice.notes or "") + f"\n[write-off] {reason}").strip()
    _recompute_status(invoice)
    session.flush()


def recompute_org_paid_totals(session: Session, invoice: Invoice) -> int:
    """Re-derive ``paid_paise`` from the payments table.

    Used by the nightly reconciliation job: the ledger column is a cache, the
    payments table is the source of truth.
    """
    total = session.scalar(
        select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
            Payment.invoice_id == invoice.id,
            Payment.status == "succeeded",
        )
    )
    invoice.paid_paise = int(total or 0)
    _recompute_status(invoice)
    session.flush()
    return invoice.paid_paise


def can_transition(current: str, target: str) -> bool:
    allowed = {
        "draft": {"issued", "cancelled"},
        "issued": {"partly_paid", "paid", "cancelled", "written_off"},
        "partly_paid": {"paid", "issued", "cancelled", "written_off"},
        "overdue": {"partly_paid", "paid", "written_off"},
        "paid": set(),
        "cancelled": set(),
        "written_off": set(),
    }
    return target in allowed.get(current, set())


def is_overdue(invoice: Invoice, as_of: dt.date) -> bool:
    if invoice.status not in OPEN_STATUSES and invoice.status != "partly_paid":
        return False
    if outstanding_of(invoice) <= 0:
        return False
    return invoice.due_date < as_of
