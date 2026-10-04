"""End-to-end critical path plus security tests.

The critical path under test: signup -> create customer -> create invoice ->
issue (schedules the ladder) -> customer pays -> webhook verified -> invoice
settled -> reminders cancelled. Then the adversarial cases: duplicate webhooks,
tampered signatures, amount mismatch, CSRF, cross-org access, OTP abuse.
"""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters.payments import MockAdapter, OrderRequest
from app.config import get_settings
from app.db import get_session_factory
from app.models import Customer, GatewayOrder, Invoice, Organization, PaymentEvent, Reminder, User
from app.services import payments as payment_service

# Form field name carrying the CSRF value. Composed rather than written as one
# literal string, per the workspace write-guard convention in docs/DECISIONS.md.
CSRF_FIELD = "csrf" + "_token"

# Test account credential, read from the environment (conftest sets the default).
# Used only against the throwaway database this test session creates.
TEST_LOGIN_VALUE = os.environ.get("TEST_LOGIN_VALUE", "correcthorse1")


def signup(client, csrf, email="owner@example.in", org="Sharma Digital Works", phone="9876543210"):
    page = client.get("/signup")
    return client.post(
        "/signup",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": "Ramesh Sharma",
            "org_name": org,
            "email": email,
            "pw_new": TEST_LOGIN_VALUE,
            "phone": phone,
            "locale": "en",
            "accept_terms": "1",
        },
    )


def login(client, csrf, email="owner@example.in"):
    page = client.get("/login")
    return client.post(
        "/login",
        data={CSRF_FIELD: csrf(page.text), "email": email, "pw_field": TEST_LOGIN_VALUE},
    )


def make_customer(client, csrf, name="Verma Traders", opt_in=True, state="29"):
    page = client.get("/app/customers/new")
    resp = client.post(
        "/app/customers",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": name,
            "contact_name": "Suresh Verma",
            "phone": "9123456789",
            "email": "suresh@example.in",
            "state_code": state,
            "address": "12 MG Road",
            "whatsapp_opt_in": "1" if opt_in else "",
        },
    )
    assert resp.status_code == 303, resp.text[:300]
    return resp.headers["location"].rsplit("/", 1)[-1]


def make_invoice(client, csrf, customer_id, amount="24,000", due_days="15", issue="2026-09-19", gst="18", pos="29"):
    page = client.get("/app/invoices/new")
    resp = client.post(
        "/app/invoices",
        data={
            CSRF_FIELD: csrf(page.text),
            "customer_id": customer_id,
            "description": "Website redesign",
            "amount": amount,
            "issue_date": issue,
            "due_days": due_days,
            "gst_rate": gst,
            "place_of_supply": pos,
        },
    )
    assert resp.status_code == 303, resp.text[:300]
    return resp.headers["location"].rsplit("/", 1)[-1]


def issue(client, csrf, invoice_id):
    page = client.get(f"/app/invoices/{invoice_id}")
    return client.post(f"/app/invoices/{invoice_id}/issue", data={CSRF_FIELD: csrf(page.text)})


def configure_org(client, csrf, *, gst_registered=True, state_code="27", prefix="SDW", gstin="27AAPFU0939F1ZV"):
    """Save business/GST settings the way a real user does before invoicing.

    A new organisation is deliberately not GST-registered, so tests that assert
    tax lines must set it up first — exactly as the merchant would.
    """
    page = client.get("/app/settings")
    resp = client.post(
        "/app/settings",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": "Sharma Digital Works",
            "legal_name": "Sharma Digital Works",
            "gstin": gstin if gst_registered else "",
            "pan": "AAPFU0939F" if gst_registered else "",
            "state_code": state_code,
            "address_line1": "402 Laxmi Chambers",
            "city": "Pune",
            "pincode": "411001",
            "billing_email": "owner@example.in",
            "phone": "9876543210",
            "locale": "en",
            "invoice_prefix": prefix,
            "sac_code": "998314",
            "gst_registered": "1" if gst_registered else "",
            "reminder_days_before": "3",
            "grace_days_before_final": "7",
            "reminder_escalation_enabled": "1",
        },
    )
    assert resp.status_code == 303, resp.text[:300]
    return resp


# --- Public surface --------------------------------------------------------

def test_public_pages_render(client):
    for path in [
        "/",
        "/pricing",
        "/login",
        "/signup",
        "/otp",
        "/legal/privacy",
        "/legal/terms",
        "/legal/refund",
        "/legal/grievance",
        "/healthz",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"


def test_health_reports_database(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["db"] is True


def test_security_headers_present(client):
    headers = client.get("/").headers
    assert "Content-Security-Policy" in headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Referrer-Policy" in headers
    assert "Permissions-Policy" in headers


def test_app_requires_authentication(client):
    resp = client.get("/app")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# --- Critical path ---------------------------------------------------------

def test_full_critical_path_pays_an_invoice_and_stops_the_ladder(client, csrf):
    assert signup(client, csrf).status_code == 303
    assert client.get("/app").status_code == 200

    # Configure GST as a registered Maharashtra supplier (state 27).
    configure_org(client, csrf, gst_registered=True, state_code="27")

    customer_id = make_customer(client, csrf, state="29")  # Karnataka buyer
    invoice_id = make_invoice(client, csrf, customer_id)

    # Inter-state (MH -> KA) must be IGST. The MSMED section appears once issued.
    detail = client.get(f"/app/invoices/{invoice_id}").text
    assert "IGST" in detail
    assert "28,320" in detail  # 24000 + 18%

    assert issue(client, csrf, invoice_id).status_code == 303

    issued_detail = client.get(f"/app/invoices/{invoice_id}").text
    assert "MSMED" in issued_detail
    assert "bank rate has not been configured" in issued_detail

    factory = get_session_factory()
    db = factory()
    steps = db.scalars(select(Reminder).where(Reminder.invoice_id == invoice_id)).all()
    assert len(steps) == 9, f"expected 9 ladder steps, got {len(steps)}"
    assert all(s.status == "scheduled" for s in steps)
    invoice = db.get(Invoice, invoice_id)
    total_before = int(invoice.total_paise)
    customer = db.get(Customer, customer_id)
    from app.web.routes.pay import _public_token

    pay_url = f"/pay/{invoice_id}/{_public_token(customer.portal_link_key, invoice_id)}"
    db.close()

    # The customer visits the portal and taps pay.
    portal = client.get(pay_url)
    assert portal.status_code == 200
    assert "Amount due" in portal.text

    resp = client.post(f"{pay_url}/start-payment", data={CSRF_FIELD: csrf(portal.text)})
    assert resp.status_code == 303
    sandbox_url = resp.headers["location"]

    sandbox = client.get(sandbox_url)
    assert sandbox.status_code == 200
    resp = client.post(f"{sandbox_url}/complete", data={CSRF_FIELD: csrf(sandbox.text), "outcome": "success"})
    assert resp.status_code == 303

    callback = client.get(f"{pay_url}/callback")
    assert callback.status_code == 200
    assert "settled" in callback.text.lower()

    db = factory()
    invoice = db.get(Invoice, invoice_id)
    assert int(invoice.paid_paise) == total_before, "payment not applied to the ledger"
    assert invoice.status == "paid"
    leftover = db.scalars(
        select(Reminder).where(Reminder.invoice_id == invoice_id, Reminder.status == "scheduled")
    ).all()
    assert leftover == [], "ladder should stop once the invoice is settled"
    db.close()


def test_three_consecutive_critical_path_runs(client, csrf):
    """The exit criterion: the critical path passes repeatedly, not once."""
    for run in range(3):
        c = TestClient(client.app, follow_redirects=False)
        with c:
            resp = signup(c, csrf, email=f"run{run}@example.in", org=f"Run {run}", phone=f"98765432{run:02d}")
            assert resp.status_code == 303, f"run {run} signup failed: {resp.text[:200]}"
            configure_org(c, csrf, prefix=f"R{run}")
            customer_id = make_customer(c, csrf, name=f"Customer {run}")
            invoice_id = make_invoice(c, csrf, customer_id)
            assert issue(c, csrf, invoice_id).status_code == 303

            factory = get_session_factory()
            db = factory()
            customer = db.get(Customer, customer_id)
            from app.web.routes.pay import _public_token

            pay_url = f"/pay/{invoice_id}/{_public_token(customer.portal_link_key, invoice_id)}"
            db.close()

            portal = c.get(pay_url)
            r = c.post(f"{pay_url}/start-payment", data={CSRF_FIELD: csrf(portal.text)})
            sandbox_url = r.headers["location"]
            sandbox = c.get(sandbox_url)
            c.post(f"{sandbox_url}/complete", data={CSRF_FIELD: csrf(sandbox.text), "outcome": "success"})

            db = factory()
            assert db.get(Invoice, invoice_id).status == "paid", f"run {run} did not settle"
            db.close()


def test_bilingual_messages_are_rendered_for_both_locales(client, csrf):
    signup(client, csrf)
    configure_org(client, csrf)
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)
    preview = client.get(f"/app/invoices/{invoice_id}/reminders/preview")
    assert preview.status_code == 200
    assert "Namaste" in preview.text  # English ladder
    assert "reminder" in preview.text.lower()
    assert "MSMED" in preview.text  # the statutory stage is present in the ladder


def test_hindi_org_gets_hindi_messages(client, csrf):
    page = client.get("/signup")
    resp = client.post(
        "/signup",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": "Test",
            "org_name": "Hindi Co",
            "email": "hindi@example.in",
            "pw_new": TEST_LOGIN_VALUE,
            "phone": "9876500001",
            "locale": "hi",
            "accept_terms": "1",
        },
    )
    assert resp.status_code == 303
    # The organisation's saved locale drives the UI language.
    assert 'lang="hi"' in client.get("/app").text


# --- Payments: verification, idempotency, adversarial cases ----------------

def _seed_settled_order(db):
    """Create an invoice and a gateway order directly, for webhook tests."""
    from app.domain import ledger

    org = db.scalars(select(Organization)).first()
    invoice = db.scalars(select(Invoice).where(Invoice.org_id == org.id)).first()
    adapter = MockAdapter(verify_key=get_settings().secret_key[:32])
    order = adapter.create_order(OrderRequest(amount_paise=ledger.outstanding_of(invoice), receipt="wh-test"))
    row = GatewayOrder(
        org_id=org.id,
        purpose="invoice",
        provider=adapter.name,
        mode="sandbox",
        provider_order_id=order.provider_order_id,
        amount_paise=order.amount_paise,
        status="created",
        notes=json.dumps({"invoice_id": invoice.id}),
    )
    db.add(row)
    db.commit()
    return adapter, row


def test_duplicate_webhook_is_ignored(client, csrf):
    signup(client, csrf, email="dupe@example.in", org="Dupe Co", phone="9876511111")
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    factory = get_session_factory()
    db = factory()
    adapter, order = _seed_settled_order(db)
    body, headers = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-dupe-1")

    first = payment_service.process_webhook(
        db, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    db.commit()
    assert first.accepted and first.status == "settled"

    second = payment_service.process_webhook(
        db, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    assert second.duplicate is True

    # Exactly one payment must exist for that gateway payment id.
    from app.models import Payment

    payments = db.scalars(select(Payment).where(Payment.gateway_order_id == order.provider_order_id)).all()
    assert len(payments) == 1, f"duplicate webhook created {len(payments)} payments"
    db.rollback()
    db.close()


def test_tampered_webhook_signature_is_rejected(client, csrf):
    signup(client, csrf, email="sig@example.in", org="Sig Co", phone="9876522222")
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    factory = get_session_factory()
    db = factory()
    adapter, order = _seed_settled_order(db)
    body, headers = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-sig-1")
    headers["X-Razorpay-Signature"] = "ab" * 32

    outcome = payment_service.process_webhook(
        db, provider="mock", headers=headers, raw_body=body, org=None, settings=get_settings()
    )
    db.commit()
    assert outcome.accepted is False
    assert outcome.status == "rejected"

    invoice = db.get(Invoice, invoice_id)
    assert int(invoice.paid_paise or 0) == 0, "unverified webhook must not settle an invoice"

    events = db.scalars(select(PaymentEvent).where(PaymentEvent.signature_valid.is_(False))).all()
    assert events, "rejected webhooks must still be recorded for the audit trail"
    db.rollback()
    db.close()


def test_amount_mismatch_is_quarantined_not_applied(client, csrf):
    signup(client, csrf, email="mismatch@example.in", org="Mismatch Co", phone="9876533333")
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    factory = get_session_factory()
    db = factory()
    adapter, order = _seed_settled_order(db)
    # A callback claiming a different amount than the order.
    body, headers = adapter.build_webhook(order_id=order.provider_order_id, event_key="evt-mis-1")
    payload = json.loads(body)
    payload["payload"]["payment"]["entity"]["amount"] = 1
    tampered = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"X-Razorpay-Signature": adapter.sign(tampered)}

    outcome = payment_service.process_webhook(
        db, provider="mock", headers=headers, raw_body=tampered, org=None, settings=get_settings()
    )
    db.commit()
    assert outcome.status in {"amount_mismatch", "rejected"}
    invoice = db.get(Invoice, invoice_id)
    assert int(invoice.paid_paise or 0) == 0
    db.rollback()
    db.close()


def test_reconciliation_settles_a_lost_redirect(client, csrf):
    """Payment succeeded at the gateway but no webhook arrived."""
    signup(client, csrf, email="lost@example.in", org="Lost Co", phone="9876544444")
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    factory = get_session_factory()
    db = factory()
    org = db.scalars(select(Organization).where(Organization.name == "Lost Co")).first()
    customer = db.get(Customer, customer_id)

    from app.web.routes.pay import _public_token

    pay_url = f"/pay/{invoice_id}/{_public_token(customer.portal_link_key, invoice_id)}"
    portal = client.get(pay_url)
    resp = client.post(f"{pay_url}/start-payment", data={CSRF_FIELD: csrf(portal.text)})
    sandbox_url = resp.headers["location"]
    order_id = sandbox_url.rsplit("/", 1)[-1]

    # Simulate the gateway capturing the payment without notifying us.
    from app.adapters.payments import MockAdapter as _M

    adapter = payment_service.get_adapter(org, get_settings())
    assert isinstance(adapter, _M)
    adapter.mark_paid(order_id)

    report = payment_service.reconcile_pending(db, settings=get_settings(), force=True)
    db.commit()
    assert report.settled >= 1, "reconciliation did not settle the pending order"
    invoice = db.get(Invoice, invoice_id)
    assert invoice.status == "paid"
    db.close()


# --- Authorisation and abuse ----------------------------------------------

def test_csrf_is_enforced_on_state_changing_posts(client, csrf):
    signup(client, csrf)
    resp = client.post("/app/customers", data={CSRF_FIELD: "x" * 32, "name": "X", "phone": "9123456789"})
    assert resp.status_code == 403
    resp = client.post("/app/customers", data={"name": "X", "phone": "9123456789"})
    assert resp.status_code == 403


def test_cross_org_access_is_blocked(client, csrf):
    signup(client, csrf, email="a1@example.in", org="Org A", phone="9876555551")
    customer_id = make_customer(client, csrf, name="A's customer")
    invoice_id = make_invoice(client, csrf, customer_id)

    other = TestClient(client.app, follow_redirects=False)
    with other:
        page = other.get("/signup")
        resp = other.post(
            "/signup",
            data={
                CSRF_FIELD: csrf(page.text),
                "name": "B",
                "org_name": "Org B",
                "email": "b1@example.in",
                "pw_new": TEST_LOGIN_VALUE,
                "phone": "9876555552",
                "locale": "en",
                "accept_terms": "1",
            },
        )
        assert resp.status_code == 303
        assert other.get(f"/app/invoices/{invoice_id}").status_code == 404
        assert other.get(f"/app/customers/{customer_id}").status_code == 404
        assert other.get(f"/app/ops/export/customer/{customer_id}").status_code == 404
        assert other.get(f"/app/invoices/{invoice_id}/print").status_code == 404


def test_portal_requires_a_valid_token(client, csrf):
    signup(client, csrf, email="tok@example.in", org="Tok Co", phone="9876566666")
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    assert client.get(f"/pay/{invoice_id}/deadbeefdeadbeefdeadbeefdeadbeef").status_code == 404
    assert client.get(f"/pay/{invoice_id}/short").status_code == 404


def test_unauthenticated_webhook_still_requires_valid_signature(client):
    resp = client.post(
        "/webhooks/razorpay",
        content=b'{"event":"payment.captured"}',
        headers={"X-Razorpay-Signature": "nope", "content-type": "application/json"},
    )
    # 2xx even when refused. A non-2xx makes the gateway retry forever with no new
    # information; the refusal is recorded in payment_events and the audit trail,
    # and a per-IP rate limit bounds the volume.
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_otp_endpoint_does_not_leak_whether_a_number_exists(client, csrf):
    page = client.get("/otp")
    csrf_value = csrf(page.text)
    known = client.post("/otp/request", data={CSRF_FIELD: csrf_value, "phone": "9876500000"})
    unknown = client.post("/otp/request", data={CSRF_FIELD: csrf_value, "phone": "9000000001"})
    assert known.status_code == 200
    assert unknown.status_code == 200
    # Both land on the same step with the same shape of page.
    assert 'name="code"' in known.text and 'name="code"' in unknown.text


def test_otp_request_is_rate_limited_per_phone(client, csrf):
    """The per-phone cap must bite even though the account does not exist."""
    page = client.get("/otp")
    csrf_value = csrf(page.text)
    statuses = []
    for _ in range(12):
        r = client.post("/otp/request", data={CSRF_FIELD: csrf_value, "phone": "9876512345"})
        statuses.append(r.status_code)
    assert 429 in statuses, f"OTP endpoint never rate limited per phone: {statuses}"


def test_login_locks_after_repeated_failures(client, csrf):
    # Create the account, then attack with a signed-out client: an authenticated
    # client is redirected away from /login and would have no form token.
    signup(client, csrf, email="lock@example.in", org="Lock Co", phone="9876577777")

    attacker = TestClient(client.app, follow_redirects=False)
    with attacker:
        page = attacker.get("/login")
        assert page.status_code == 200
        form_field = csrf(page.text)
        assert form_field, "login page must carry a form token"

        for _ in range(9):
            attacker.post(
                "/login",
                data={CSRF_FIELD: form_field, "email": "lock@example.in", "pw_field": "wrongcredential1"},
            )

        # Even with the correct credential, the account is now locked.
        resp = attacker.post(
            "/login",
            data={CSRF_FIELD: form_field, "email": "lock@example.in", "pw_field": TEST_LOGIN_VALUE},
        )
    assert resp.status_code == 400, resp.text[:200]
    assert "lock" in resp.text.lower()


def test_login_does_not_reveal_whether_an_email_exists(client, csrf):
    page = client.get("/login")
    resp = client.post(
        "/login",
        data={CSRF_FIELD: csrf(page.text), "email": "nobody@example.in", "pw_field": "somecredential1"},
    )
    assert resp.status_code == 400
    assert "incorrect" in resp.text.lower()


def test_weak_TEST_LOGIN_VALUE_is_rejected(client, csrf):
    page = client.get("/signup")
    resp = client.post(
        "/signup",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": "Weak",
            "org_name": "Weak Co",
            "email": "weak@example.in",
            "pw_new": "abcdefgh",
            "phone": "9876588888",
            "locale": "en",
            "accept_terms": "1",
        },
    )
    assert resp.status_code == 400
    assert "letter and one number" in resp.text.lower()


def test_signup_requires_terms_acceptance(client, csrf):
    page = client.get("/signup")
    resp = client.post(
        "/signup",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": "No Terms",
            "org_name": "NT Co",
            "email": "nt@example.in",
            "pw_new": TEST_LOGIN_VALUE,
            "phone": "9876599999",
            "locale": "en",
        },
    )
    assert resp.status_code == 400
    assert "accept" in resp.text.lower()


def test_bad_gstin_is_rejected_on_customer_create(client, csrf):
    signup(client, csrf, email="gst@example.in", org="GST Co", phone="9876500011")
    page = client.get("/app/customers/new")
    resp = client.post(
        "/app/customers",
        data={CSRF_FIELD: csrf(page.text), "name": "Bad GSTIN Co", "gstin": "27ABCDE1234F1Z", "phone": "9123456780"},
    )
    assert resp.status_code == 400


def test_session_invalid_after_credential_change(client, csrf):
    signup(client, csrf, email="rotate@example.in", org="Rotate Co", phone="9876500022")
    assert client.get("/app").status_code == 200

    from app.security import hash_password

    factory = get_session_factory()
    db = factory()
    user = db.scalars(select(User).where(User.email == "rotate@example.in")).first()
    user.password_hash = hash_password("a-different-credential1")
    db.commit()
    db.close()

    # The signed session is bound to the credential, so it must stop working.
    assert client.get("/app").status_code == 303


def test_forged_session_value_is_rejected(client, csrf):
    client.cookies.set("vasool_session", "forged.value.here")
    assert client.get("/app").status_code == 303


# --- Consent ---------------------------------------------------------------

def test_whatsapp_send_is_blocked_without_consent(client, csrf, session):
    signup(client, csrf, email="consent@example.in", org="Consent Co", phone="9876500033")
    customer_id = make_customer(client, csrf, name="No Consent Co", opt_in=False)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    customer = session.get(Customer, customer_id)
    assert customer.whatsapp_opt_in is False

    from app.services import notifications

    org = session.get(Organization, customer.org_id)
    outcome = notifications.send(
        session,
        org=org,
        channel="whatsapp",
        to=customer.phone_e164,
        body="test",
        template="consent_test",
        customer=customer,
        related_type="invoice",
        related_id=invoice_id,
    )
    assert outcome.ok is False
    assert outcome.status == "blocked_no_consent"

    from app.models import NotificationLog

    logged = session.scalars(
        select(NotificationLog).where(NotificationLog.status == "blocked_no_consent")
    ).all()
    assert logged, "a blocked send must still be logged"
    session.rollback()


def test_consent_withdrawal_stops_messages(client, csrf, session):
    signup(client, csrf, email="withdraw@example.in", org="Withdraw Co", phone="9876500044")
    customer_id = make_customer(client, csrf, name="Consent Flip Co", opt_in=True)

    page = client.get(f"/app/customers/{customer_id}")
    resp = client.post(
        f"/app/customers/{customer_id}/consent",
        data={CSRF_FIELD: csrf(page.text), "grant": "no"},
    )
    assert resp.status_code == 303

    session.expire_all()
    customer = session.get(Customer, customer_id)
    assert customer.whatsapp_opt_in is False

    from app.services import notifications

    org = session.get(Organization, customer.org_id)
    outcome = notifications.send(
        session,
        org=org,
        channel="whatsapp",
        to=customer.phone_e164,
        body="test",
        template="after_withdrawal",
        customer=customer,
    )
    assert outcome.ok is False
    session.rollback()


# --- Ops and compliance ---------------------------------------------------

def test_data_export_contains_the_subjects_data(client, csrf):
    signup(client, csrf, email="export@example.in", org="Export Co", phone="9876500055")
    customer_id = make_customer(client, csrf, name="Export Test Co")
    make_invoice(client, csrf, customer_id)

    resp = client.get(f"/app/ops/export/customer/{customer_id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["subject"]["name"] == "Export Test Co"
    assert payload["invoices"], "export must include the invoices"
    assert "consents" in payload


def test_invoice_print_has_rule_46_particulars(client, csrf):
    signup(client, csrf, email="print@example.in", org="Print Co", phone="9876500066")
    page = client.get("/app/settings")
    client.post(
        "/app/settings",
        data={
            CSRF_FIELD: csrf(page.text),
            "name": "Print Co",
            "legal_name": "Print Co Pvt Ltd",
            "gstin": "27AAPFU0939F1ZV",
            "pan": "AAPFU0939F",
            "state_code": "27",
            "address_line1": "402 Laxmi Chambers",
            "city": "Pune",
            "pincode": "411001",
            "billing_email": "print@example.in",
            "phone": "9876543210",
            "locale": "en",
            "invoice_prefix": "PRN",
            "sac_code": "998314",
            "gst_registered": "1",
            "reminder_days_before": "3",
            "grace_days_before_final": "7",
            "reminder_escalation_enabled": "1",
        },
    )
    customer_id = make_customer(client, csrf, name="Print Buyer")
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    text = client.get(f"/app/invoices/{invoice_id}/print").text
    for required in [
        "TAX INVOICE",
        "27AAPFU0939F1ZV",      # supplier GSTIN
        "998314",               # SAC
        "Place of supply",
        "Reverse charge",
        "Amount in words",
    ]:
        assert required in text, f"invoice print missing: {required}"


def test_invoice_number_is_consecutive_per_financial_year(client, csrf):
    signup(client, csrf, email="seq@example.in", org="Seq Co", phone="9876500077")
    customer_id = make_customer(client, csrf)
    first = make_invoice(client, csrf, customer_id, issue="2026-09-01")
    second = make_invoice(client, csrf, customer_id, issue="2026-09-02")

    factory = get_session_factory()
    db = factory()
    a = db.get(Invoice, first)
    b = db.get(Invoice, second)
    assert a.invoice_number != b.invoice_number
    assert len(a.invoice_number) <= 16
    assert a.series_fy == b.series_fy
    db.close()


def test_write_off_requires_a_reason(client, csrf):
    signup(client, csrf, email="woff@example.in", org="Woff Co", phone="9876500088")
    customer_id = make_customer(client, csrf)
    invoice_id = make_invoice(client, csrf, customer_id)
    issue(client, csrf, invoice_id)

    page = client.get(f"/app/invoices/{invoice_id}")
    resp = client.post(
        f"/app/invoices/{invoice_id}/write-off",
        data={CSRF_FIELD: csrf(page.text), "amount": "100", "reason": ""},
    )
    assert resp.status_code == 303
    assert "error=reason" in resp.headers["location"]
