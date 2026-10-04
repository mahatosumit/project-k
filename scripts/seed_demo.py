"""Seed a realistic demo dataset so the app can be walked by hand.

Creates one organisation, three customers, four invoices in different recovery
stages, and runs the payment flow for one of them. Uses only the public service
layer, so the seeded rows obey the same invariants as real ones.

    python scripts/seed_demo.py                 # build the demo data
    python scripts/seed_demo.py --with-demo-payment

Never run this against production: it refuses unless APP_ENV is dev.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.db import run_migrations, session_scope
from app.domain import ledger
from app.domain.gst import compute_tax, invoice_number_for, series_for
from app.domain.money import financial_year, rupees_to_paise, today_ist
from app.models import Counter, Customer, Invoice, InvoiceItem, Organization
from app.security import new_token
from app.services import auth as auth_service
from app.services import notifications
from app.services import payments as payment_service
from app.services import reminders as reminder_service

DEMO_CREDENTIAL = "demo-account-123"
CUSTOMERS = [
    ("Verma Traders", "Suresh Verma", "9123456789", "suresh@example.in", "29", "12 MG Road, Bengaluru", True),
    ("Kapoor Interiors", "Anita Kapoor", "9823456780", "anita@example.in", "27", "7 FC Road, Pune", True),
    ("Nair Logistics", "Deepak Nair", "9744567812", None, "32", "Kochi, Kerala", False),
]
INVOICES = [
    # (customer index, description, amount, days until due, gst rate, state)
    (0, "Website redesign and hosting", "24,000", 12, 18, "29"),
    (1, "Shop fit-out consulting", "1,50,000", -7, 18, "27"),
    (2, "Freight dashboard maintenance", "48,000", -48, 18, "32"),
    (1, "Annual retainer — October", "35,000", -100, 18, "27"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument("--with-demo-payment", action="store_true", help="also settle the first invoice")
    args = parser.parse_args()

    settings = get_settings()
    if settings.environment != "dev":
        raise SystemExit("Refusing to seed demo data outside APP_ENV=dev.")

    run_migrations()
    today = today_ist()

    with session_scope() as session:
        if session.query(Organization).filter(Organization.name == "Sharma Digital Works").first():
            print("Demo organisation already exists; nothing to do.")
            return 0

        user, org = auth_service.create_account(
            session,
            email="demo@vasool.example.in",
            secret_text=DEMO_CREDENTIAL,
            name="Ramesh Sharma",
            org_name="Sharma Digital Works",
            phone_e164="+919876500000",
            locale="en",
        )
        org.legal_name = "Sharma Digital Works"
        org.gstin = "27AAPFU0939F1ZV"
        org.pan = "AAPFU0939F"
        org.state_code = "27"
        org.state = "Maharashtra"
        org.city = "Pune"
        org.address_line1 = "402 Laxmi Chambers, FC Road"
        org.pincode = "411001"
        org.billing_email = "ramesh@sharmadigital.example.in"
        org.invoice_prefix = "SDW"
        org.sac_code = "998314"
        org.gst_registered = True
        org.complaint_officer_name = "Ramesh Sharma"
        org.complaint_officer_email = "grievance@sharmadigital.example.in"
        org.complaint_officer_phone = "+919876500000"
        org.gateway_provider = "mock"
        org.gateway_key_id = "mock_key_demo"
        org.gateway_status = "connected"
        session.flush()

        customers = []
        for name, contact, phone, email, state, address, opt_in in CUSTOMERS:
            customer = Customer(
                org_id=org.id,
                name=name,
                contact_name=contact,
                phone_e164=f"+91{phone}",
                email=email,
                state_code=state,
                address=address,
                portal_link_key=new_token(),
                whatsapp_opt_in=False,
            )
            session.add(customer)
            session.flush()
            if opt_in:
                notifications.grant_consent(
                    session, org_id=org.id, customer=customer, source="demo_seed", evidence="demo data"
                )
            customers.append(customer)

        created: list[Invoice] = []
        fy = financial_year(today)
        for index, (ci, description, amount, due_in, rate, pos) in enumerate(INVOICES, start=1):
            sub_total = rupees_to_paise(amount)
            tax = compute_tax(
                subtotal_paise=sub_total,
                supplier_state_code=org.state_code,
                place_of_supply_state_code=pos,
                gst_registered=True,
                gst_rate_percent=rate,
            )
            counter_key = f"invoice:{org.id}:{fy}"
            counter = session.get(Counter, counter_key) or Counter(name=counter_key, value=0)
            counter.value = index
            session.merge(counter)

            issue_date = today + dt.timedelta(days=due_in - 15)
            invoice = Invoice(
                org_id=org.id,
                customer_id=customers[ci].id,
                invoice_number=invoice_number_for(org.invoice_prefix, fy, index),
                series_fy=series_for(issue_date, org.invoice_prefix),
                issue_date=issue_date,
                due_date=today + dt.timedelta(days=due_in),
                sac_code=org.sac_code,
                description=description,
                place_of_supply_state_code=pos,
                is_interstate=tax.is_interstate,
                taxable_value_paise=tax.taxable_value_paise,
                gst_rate_percent=tax.gst_rate_percent,
                cgst_paise=tax.cgst_paise,
                sgst_paise=tax.sgst_paise,
                igst_paise=tax.igst_paise,
                total_paise=tax.total_paise,
                status="issued",
                created_by=user.id,
            )
            session.add(invoice)
            session.flush()
            session.add(
                InvoiceItem(
                    invoice_id=invoice.id,
                    seq=1,
                    description=description,
                    hsn_sac=org.sac_code,
                    quantity=1,
                    unit="NOS",
                    unit_price_paise=sub_total,
                    line_total_paise=sub_total,
                )
            )
            reminder_service.schedule_invoice(session, invoice, org)
            created.append(invoice)

        # Pay part of the second invoice so the ledger shows a real part-payment.
        second = created[1]
        ledger.record_payment(
            session,
            invoice=second,
            amount_paise=rupees_to_paise("50,000"),
            method="bank_transfer",
            reference="NEFT/2026/88431",
            utr="88431",
            notes="Demo part payment",
            recorded_by=user.id,
        )

        if args.with_demo_payment:
            first = created[0]
            try:
                order, _checkout = payment_service.create_invoice_payment_order(
                    session,
                    org=org,
                    invoice=first,
                    customer=customers[0],
                    return_url=f"{settings.base_url}/pay/{first.id}/callback",
                )
                from app.adapters.payments import MockAdapter

                adapter = payment_service.get_adapter(org, settings)
                if isinstance(adapter, MockAdapter):
                    adapter.mark_paid(order.provider_order_id)
                    body, headers = adapter.build_webhook(
                        order_id=order.provider_order_id, event_key=f"seed-{order.provider_order_id}"
                    )
                    payment_service.process_webhook(
                        session,
                        provider=adapter.name,
                        headers=headers,
                        raw_body=body,
                        org=org,
                        settings=settings,
                    )
            except Exception as exc:
                print(f"demo payment skipped: {type(exc).__name__}")

        print("Demo data created.")
        print("  login:  demo@vasool.example.in")
        print(f"  pass:   {DEMO_CREDENTIAL}")
        print(f"  org:    {org.name} ({org.gstin})")
        print(f"  invoices: {len(created)}")
        for invoice in created:
            amount = ledger.outstanding_of(invoice)
            print(f"    {invoice.invoice_number} due {invoice.due_date} outstanding {amount / 100:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
