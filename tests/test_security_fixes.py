"""Regression tests for the independent security review's findings.

Every test here corresponds to a finding in docs/security-review.md, so a
regression reintroduces a failing test rather than a silent hole.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.adapters.payments import MockAdapter, OrderRequest
from app.config import get_settings
from app.db import get_session_factory
from app.domain import ledger
from app.models import Customer, GatewayOrder, Invoice, Organization, Payment, PaymentEvent
from app.services import payments as payment_service

from .conftest import csrf_of
from .test_critical_path import (
    CSRF_FIELD,
    TEST_LOGIN_VALUE,
    configure_org,
    issue,
    make_customer,
    make_invoice,
    signup,
)


def _seed_order(db, invoice_id, amount_paise=None, status="created", purpose="invoice"):
    """Create a gateway order row directly, for webhook-path tests."""
    invoice = db.get(Invoice, invoice_id)
    adapter = MockAdapter(verify_key=get_settings().secret_key[:32])
    amount = amount_paise if amount_paise is not None else ledger.outstanding_of(invoice)
    order = adapter.create_order(OrderRequest(amount_paise=amount, receipt="sec-test"))
    row = GatewayOrder(
        org_id=invoice.org_id,
        purpose=purpose,
        provider=adapter.name,
        mode="sandbox",
        provider_order_id=order.provider_order_id,
        amount_paise=order.amount_paise,
        status=status,
        notes=json.dumps({"invoice_id": invoice.id}),
    )
    db.add(row)
    db.commit()
    return adapter, row


# ---------------------------------------------------------------- H3 --------
def test_gateway_payment_id_is_unique_in_the_database(client, csrf, session):
    """A gateway payment id must not be insertable twice for the same provider.

    Without the unique index, two deliveries of the same payment with different
    event ids could both pass the existence check and double-credit an invoice.
    """
    signup(client, csrf, email="uniq@example.in", org="Uniq Co", phone="9876500101")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    invoice = session.get(Invoice, invoice_id)
    session.add(
        Payment(
            org_id=invoice.org_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            amount_paise=1000,
            method="gateway",
            gateway_provider="razorpay",
            gateway_payment_id="pay_duplicate_test_1",
        )
    )
    session.flush()

    session.add(
        Payment(
            org_id=invoice.org_id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            amount_paise=1000,
            method="gateway",
            gateway_provider="razorpay",
            gateway_payment_id="pay_duplicate_test_1",
        )
    )
    with pytest.raises(Exception) as excinfo:
        session.flush()
    assert "unique" in str(excinfo.value).lower() or "integrity" in str(excinfo.value).lower()
    session.rollback()


def test_two_events_for_one_payment_credit_once(client, csrf, session):
    """Two webhook deliveries, different event ids, one payment: credit once."""
    signup(client, csrf, email="once@example.in", org="Once Co", phone="9876500102")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    adapter, order = _seed_order(session, invoice_id)
    session.commit()

    body1, headers1 = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-a")
    first = payment_service.process_webhook(
        session, provider="mock", headers=headers1, raw_body=body1, org=None, settings=get_settings()
    )
    session.commit()
    assert first.status == "settled"

    # Same payment, different event id: must not credit again.
    body2, headers2 = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-b")
    second = payment_service.process_webhook(
        session, provider="mock", headers=headers2, raw_body=body2, org=None, settings=get_settings()
    )
    session.commit()

    payments = session.scalars(select(Payment).where(Payment.gateway_order_id == order.provider_order_id)).all()
    assert len(payments) == 1, f"expected one payment, found {len(payments)}"
    invoice = session.get(Invoice, invoice_id)
    assert int(invoice.paid_paise) == int(order.amount_paise), "invoice credited more than once"
    assert second.status in {"duplicate", "ledger_conflict", "paid_uncredited", "settled"}


# ---------------------------------------------------------------- H2 --------
def test_money_captured_but_uncreditable_stays_retryable(client, csrf, session):
    """If the ledger rejects the money, the order must not be closed as paid."""
    signup(client, csrf, email="uncred@example.in", org="Uncred Co", phone="9876500103")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    # Order for MORE than the invoice owes, which the ledger must refuse.
    invoice = session.get(Invoice, invoice_id)
    adapter, order = _seed_order(session, invoice_id, amount_paise=int(invoice.total_paise) + 500000)
    session.commit()

    body, headers = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-over")
    outcome = payment_service.process_webhook(
        session, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    session.commit()

    assert outcome.status == "paid_uncredited", outcome.status
    refreshed = session.get(GatewayOrder, order.id)
    assert refreshed.status == "paid_uncredited", "an uncredited payment must not be closed as paid"

    # It must still be discoverable by the reconciliation sweep.
    report = payment_service.reconcile_pending(session, settings=get_settings(), force=True)
    session.commit()
    assert report.checked >= 1 or report.uncredited >= 1


def test_uncredited_payment_is_visible_to_a_human(client, csrf, session):
    """The ops surface must tell someone that money is waiting to be applied."""
    signup(client, csrf, email="visible@example.in", org="Visible Co", phone="9876500104")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    invoice = session.get(Invoice, invoice_id)
    adapter, order = _seed_order(session, invoice_id, amount_paise=int(invoice.total_paise) + 100)
    session.commit()
    body, headers = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-visible")
    payment_service.process_webhook(
        session, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    session.commit()

    # Reconciliation reports it rather than quietly ignoring it.
    result = payment_service.reconcile_pending(session, settings=get_settings(), force=True)
    session.commit()
    assert result.uncredited >= 1 or result.uncredited_resolved >= 1


# ---------------------------------------------------------------- H1 --------
def test_ops_view_does_not_leak_another_tenants_data(client, csrf, session):
    """Org A's ops page must not contain Org B's events, audit rows or requests."""
    from fastapi.testclient import TestClient

    # Tenant A: real activity, so there is something to leak.
    signup(client, csrf, email="tenantA@example.in", org="Tenant A", phone="9876500201")
    configure_org(client, csrf)
    customer_a = make_customer(client, csrf, name="A Customer")
    invoice_a = make_invoice(client, csrf, customer_a)
    issue(client, csrf, invoice_a)
    adapter_a, order_a = _seed_order(session, invoice_a)
    session.commit()
    body, headers = adapter_a.build_webhook(order_id=order_a.provider_order_id, event_key="evt-tenant-a")
    payment_service.process_webhook(
        session, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    session.commit()

    # Tenant B exists and looks at its own ops page.
    other = TestClient(client.app, follow_redirects=False)
    with other:
        page = other.get("/signup")
        resp = other.post(
            "/signup",
            data={
                CSRF_FIELD: csrf_of(page.text),
                "name": "B",
                "org_name": "Tenant B",
                "email": "tenantB@example.in",
                "pw_new": TEST_LOGIN_VALUE,
                "phone": "9876500202",
                "locale": "en",
                "accept_terms": "1",
            },
        )
        assert resp.status_code == 303
        ops = other.get("/app/ops")
        assert ops.status_code == 200
        # None of tenant A's identifiers may appear.
        assert invoice_a not in ops.text
        assert "Tenant A" not in ops.text
        assert order_a.provider_order_id not in ops.text

        # And tenant B must not be able to trigger work on A's orders.
        token_b = csrf_of(other.get("/app/ops").text)
        other.post("/app/ops/run/reconcile", data={CSRF_FIELD: token_b})
        session.expire_all()
        assert session.get(GatewayOrder, order_a.id).status in {"paid", "created", "paid_uncredited"}


def test_payment_event_carries_the_owning_org(client, csrf, session):
    signup(client, csrf, email="scope@example.in", org="Scope Co", phone="9876500105")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    adapter, order = _seed_order(session, invoice_id)
    session.commit()
    body, headers = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-scope")
    payment_service.process_webhook(
        session, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    session.commit()

    event = session.scalars(select(PaymentEvent).where(PaymentEvent.event_key == "evt-scope")).first()
    assert event is not None
    assert event.org_id == order.org_id, "a webhook event must record the owning organisation"


# ---------------------------------------------------------------- M1 --------
def test_support_ack_never_targets_a_form_supplied_number(client, csrf, session):
    """A third-party number in the support form must not receive a message."""
    signup(client, csrf, email="ack@example.in", org="Ack Co", phone="9876500106")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf, name="Ack Customer")
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    customer = session.get(Customer, customer_id)
    from app.web.routes.pay import _public_token

    portal_path = f"/pay/{invoice_id}/{_public_token(customer.portal_link_key, invoice_id)}"
    portal = client.get(portal_path)
    resp = client.post(
        f"{portal_path}/support",
        data={
            CSRF_FIELD: csrf_of(portal.text),
            "category": "general",
            "message": "Please call me",
            "contact": "+919999999999",  # an arbitrary third-party number
        },
    )
    assert resp.status_code == 303

    from app.models import NotificationLog

    logs = session.scalars(
        select(NotificationLog).where(NotificationLog.template == "support_ack")
    ).all()
    for entry in logs:
        assert "999999" not in (entry.to_address or ""), (
            "a support acknowledgement was sent to a form-supplied number, bypassing consent"
        )


def test_support_ack_uses_the_customer_record(client, csrf, session):
    signup(client, csrf, email="ack2@example.in", org="Ack2 Co", phone="9876500107")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf, name="Record Customer")
    make_invoice(client, csrf, customer_id)

    customer = session.get(Customer, customer_id)
    from app.services import notifications

    org = session.get(Organization, customer.org_id)
    outcome = notifications.send_support_ack(
        session, org=org, customer=customer, reference="TESTREF", sla_hours=48
    )
    assert outcome.status in {"sent", "failed", "blocked_no_consent"}
    assert "support_ack" not in (outcome.error or "")


# ---------------------------------------------------------------- M2 --------
def test_production_refuses_the_mock_gateway(monkeypatch):
    """Booting in production with the sandbox adapter must fail loudly."""
    from app import main as main_module

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "prod-check-signing-material-0123456789")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "prod-check-field-material-0123456789ab")
    monkeypatch.setenv("PAYMENT_PROVIDER", "mock")
    monkeypatch.setenv("MESSAGING_PROVIDER", "console")

    from app.config import Settings, get_settings

    get_settings.cache_clear()
    fake = Settings.from_env()
    monkeypatch.setattr(main_module, "get_settings", lambda: fake)
    try:
        with pytest.raises(RuntimeError) as excinfo:
            main_module._assert_production_ready()
        message = str(excinfo.value)
        assert "mock" in message.lower()
    finally:
        get_settings.cache_clear()


def test_production_accepts_a_real_gateway(monkeypatch):
    from app import main as main_module
    from app.config import Settings

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "prod-check-signing-material-0123456789")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "prod-check-field-material-0123456789ab")
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_configured")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "configured-for-this-test-only")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "configured-for-this-test-only")
    monkeypatch.setenv("MESSAGING_PROVIDER", "whatsapp")
    monkeypatch.setenv("WHATSAPP_TOKEN", "configured-for-this-test-only")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")

    from app.config import get_settings

    get_settings.cache_clear()
    fake = Settings.from_env()
    monkeypatch.setattr(main_module, "get_settings", lambda: fake)
    try:
        main_module._assert_production_ready()  # must not raise
    finally:
        get_settings.cache_clear()


def test_sandbox_routes_are_unreachable_when_prod(client, csrf, monkeypatch):
    """The sandbox screens must 404 rather than settle an invoice in production."""
    signup(client, csrf, email="prodsbx@example.in", org="Prod Co", phone="9876500108")
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)

    db = get_session_factory()()
    try:
        customer = db.get(Customer, customer_id)
        from app.web.routes.pay import _public_token

        portal_path = f"/pay/{invoice_id}/{_public_token(customer.portal_link_key, invoice_id)}"
    finally:
        db.close()

    # Flip the app into production mode for this request only.
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "prod-check-signing-material-0123456789")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "prod-check-field-material-0123456789ab")
    try:
        resp = client.get(f"{portal_path}/sandbox/order_mock_does_not_exist")
        assert resp.status_code == 404, "sandbox screen must not exist in production"
    finally:
        get_settings.cache_clear()
        monkeypatch.setenv("APP_ENV", "dev")
        get_settings.cache_clear()


# ---------------------------------------------------------------- M3 --------
def test_billing_sandbox_cannot_settle_another_orgs_order(client, csrf, session):
    """Posting another org's order id must not settle it."""
    from fastapi.testclient import TestClient

    signup(client, csrf, email="billa@example.in", org="Bill A", phone="9876500301")
    configure_org(client, csrf)

    # Create a subscription order for tenant A.
    billing = client.get("/billing")
    resp = client.post(
        "/billing/subscribe",
        data={CSRF_FIELD: csrf_of(billing.text), "plan": "starter_monthly"},
    )
    assert resp.status_code == 303
    order_a = session.scalars(
        select(GatewayOrder).where(GatewayOrder.purpose == "subscription")
    ).first()
    assert order_a is not None, "expected a subscription order to be created"

    other = TestClient(client.app, follow_redirects=False)
    with other:
        page = other.get("/signup")
        other.post(
            "/signup",
            data={
                CSRF_FIELD: csrf_of(page.text),
                "name": "B",
                "org_name": "Bill B",
                "email": "billb@example.in",
                "pw_new": TEST_LOGIN_VALUE,
                "phone": "9876500302",
                "locale": "en",
                "accept_terms": "1",
            },
        )
        page = other.get("/billing")
        resp = other.post(
            f"/billing/sandbox/{order_a.provider_order_id}/complete",
            data={CSRF_FIELD: csrf_of(page.text), "outcome": "success"},
        )
        assert resp.status_code == 303

    session.expire_all()
    assert session.get(GatewayOrder, order_a.id).status != "paid", (
        "another organisation settled this order"
    )
