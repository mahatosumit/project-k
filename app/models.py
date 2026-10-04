"""SQLAlchemy ORM models.

Money is integer paise everywhere. Dates are ``date``; event times are
``datetime`` (UTC, naive in the DB for portability).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.security import new_id, new_token


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    state_code: Mapped[str] = mapped_column(String(2), default="27", nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(6))
    country: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    billing_email: Mapped[str | None] = mapped_column(String(254))
    locale: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    invoice_prefix: Mapped[str] = mapped_column(String(10), default="INV", nullable=False)
    sac_code: Mapped[str] = mapped_column(String(6), default="998314", nullable=False)
    gst_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    place_of_supply_state_code: Mapped[str | None] = mapped_column(String(2))
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    reminder_escalation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    grace_days_before_final: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    complaint_officer_name: Mapped[str | None] = mapped_column(String(200))
    complaint_officer_email: Mapped[str | None] = mapped_column(String(254))
    complaint_officer_phone: Mapped[str | None] = mapped_column(String(16))
    gateway_provider: Mapped[str | None] = mapped_column(String(20))
    gateway_key_id: Mapped[str | None] = mapped_column(String(120))
    gateway_key_secret_enc: Mapped[str | None] = mapped_column(Text)
    gateway_webhook_secret_enc: Mapped[str | None] = mapped_column(Text)
    gateway_status: Mapped[str] = mapped_column(String(20), default="not_connected", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="owner", nullable=False)
    locale: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="users")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(254))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str | None] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(String(400))
    notes: Mapped[str | None] = mapped_column(Text)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opt_in_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    opt_in_source: Mapped[str | None] = mapped_column(String(60))
    portal_link_key: Mapped[str] = mapped_column(String(64), default=new_token, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("org_id", "series_fy", "invoice_number", name="ux_invoices_number"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(16), nullable=False)
    series_fy: Mapped[str] = mapped_column(String(7), nullable=False)
    issue_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    sac_code: Mapped[str] = mapped_column(String(6), default="998314", nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))
    place_of_supply_state_code: Mapped[str | None] = mapped_column(String(2))
    is_interstate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taxable_value_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    discount_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    gst_rate_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    paid_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    credited_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    written_off_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    customer: Mapped[Customer] = relationship()
    items: Mapped[list[InvoiceItem]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="invoice")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False)
    hsn_sac: Mapped[str | None] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), default=1, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="NOS", nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    line_total_paise: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="succeeded", nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    utr: Mapped[str | None] = mapped_column(String(40))
    received_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    gateway_provider: Mapped[str | None] = mapped_column(String(20))
    gateway_order_id: Mapped[str | None] = mapped_column(String(120))
    gateway_payment_id: Mapped[str | None] = mapped_column(String(120))
    gateway_signature: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    invoice: Mapped[Invoice | None] = relationship(back_populates="payments")
    customer: Mapped[Customer | None] = relationship()


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "event_key", name="ux_payment_events_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # Scopes the event to one merchant so the ops view cannot leak another
    # merchant's webhook payloads. NULL means a platform-level event, which a
    # tenant view filters out.
    org_id: Mapped[str | None] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("invoice_id", "step_index", "channel", name="ux_reminders_step"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp", nullable=False)
    tone: Mapped[str] = mapped_column(String(20), default="friendly", nullable=False)
    scheduled_for: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)
    message_body: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    invoice: Mapped[Invoice] = relationship()
    customer: Mapped[Customer] = relationship()


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    public_token: Mapped[str] = mapped_column(String(64), default=new_token, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str | None] = mapped_column(Text)
    promised_date: Mapped[dt.date | None] = mapped_column(Date)
    claimed_amount_paise: Mapped[int | None] = mapped_column(BigInteger)
    claimed_utr: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    invoice: Mapped[Invoice] = relationship()
    customer: Mapped[Customer] = relationship()


class InstallmentPlan(Base):
    __tablename__ = "installment_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    dispute_id: Mapped[str | None] = mapped_column(ForeignKey("disputes.id", ondelete="SET NULL"))
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="offered", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    installments: Mapped[list[Installment]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="Installment.seq"
    )


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (UniqueConstraint("plan_id", "seq", name="ux_installments_seq"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("installment_plans.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))

    plan: Mapped[InstallmentPlan] = relationship(back_populates="installments")


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(60), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(20), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str | None] = mapped_column(String(60))
    evidence: Mapped[str | None] = mapped_column(String(255))
    granted_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    to_address: Mapped[str] = mapped_column(String(254), nullable=False)
    template: Mapped[str | None] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    related_type: Mapped[str | None] = mapped_column(String(30))
    related_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    request_ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RateCounter(Base):
    __tablename__ = "rate_counters"
    __table_args__ = (
        UniqueConstraint("bucket", "key", "window_start", name="ux_rate_counters"),
    )

    rowid_: Mapped[int] = mapped_column("rowid", Integer, primary_key=True, autoincrement=True)
    bucket: Mapped[str] = mapped_column(String(60), nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SupportRequest(Base):
    __tablename__ = "support_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    subject_type: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(20), default="portal", nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    sla_due_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DataRequest(Base):
    __tablename__ = "data_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    subject_type: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)
    subject_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    due_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)


class BreachEvent(Base):
    __tablename__ = "breach_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reported_to_cert_in_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    report_due_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    affected_subjects: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(30), nullable=False)
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="trialing", nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    current_period_end: Mapped[dt.datetime | None] = mapped_column(DateTime)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class GatewayOrder(Base):
    __tablename__ = "gateway_orders"
    __table_args__ = (UniqueConstraint("provider", "provider_order_id", name="ux_orders_provider_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"))
    purpose: Mapped[str] = mapped_column(String(30), default="subscription", nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), default="sandbox", nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    idempotency_key: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(20), default="system", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Counter(Base):
    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
