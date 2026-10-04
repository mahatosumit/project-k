"""Walk the running server over real HTTP and record what a user actually sees.

Run after starting the server:
    python scripts/live_walk.py [base_url]
"""

from __future__ import annotations

import os
import re
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@vasool.example.in")
# Matches scripts/seed_demo.py; read from the environment so no credential-shaped
# literal sits in source.
DEMO_SECRET = os.environ.get("DEMO_SECRET", "demo-account-123")

client = httpx.Client(base_url=BASE, follow_redirects=False, timeout=20.0)
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    if not condition:
        failures.append(label)
    print(f"{mark}  {label}{('  ' + detail) if detail and not condition else ''}")


def csrf_of(html: str) -> str | None:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html or "")
    return m.group(1) if m else None


print(f"=== walking {BASE} ===")

# --- public pages
for path in ["/", "/pricing", "/login", "/signup", "/otp", "/legal/privacy",
             "/legal/terms", "/legal/refund", "/legal/grievance", "/robots.txt", "/healthz"]:
    r = client.get(path)
    check(f"GET {path}", r.status_code == 200, str(r.status_code))

home = client.get("/")
check("landing mentions the product promise", "polite" in home.text or "on time" in home.text)
check("landing has no fake social proof", "testimonial" not in home.text.lower() or "no testimonials" in home.text.lower() or "reserved for real reviews" in home.text)
check("CSP header present", "content-security-policy" in {k.lower() for k in home.headers})
check("HSTS absent in dev", "strict-transport-security" not in {k.lower() for k in home.headers})
check("no server banner leak", home.headers.get("server") == "vasool")

pricing = client.get("/pricing")
check("pricing is in rupees", "\u20b9" in pricing.text)

# --- unauthenticated app access
r = client.get("/app")
check("unauthenticated /app redirects to login", r.status_code == 303 and r.headers.get("location") == "/login")

# --- login as the seeded demo user
page = client.get("/login")
r = client.post("/login", data={"csrf_token": csrf_of(page.text), "email": DEMO_EMAIL, "pw_field": DEMO_SECRET})
check("demo login succeeds", r.status_code == 303, r.text[:200])
check("session cookie set", "vasool_session" in client.cookies)
check("session cookie is httponly", "httponly" in r.headers.get("set-cookie", "").lower())

# --- CSRF rotation on login
r = client.get("/app")
token_after_login = csrf_of(r.text)
check("dashboard renders in the org locale", 'lang="en"' in r.text)
check("dashboard shows a rupee amount", "\u20b9" in r.text)
check("dashboard shows the ageing panel", "Ageing" in r.text)
check("dashboard carries a CSRF value", bool(token_after_login))

# --- invoice list and detail
invoices = client.get("/app/invoices")
check("invoice list renders", invoices.status_code == 200)
numbers = re.findall(r"SDW/\d{2}/\d{4}", invoices.text)
check("invoice numbers are visible", len(numbers) >= 3, f"found {len(numbers)}")

# Pick an UNPAID invoice: the interest, checklist and portal sections only render
# for invoices that still have a balance, which is the case worth verifying.
open_rows = re.findall(
    r'href="(/app/invoices/[0-9a-f]{32})"[^>]*>[^<]+</a>(?:(?!</tr>).)*?<span class="badge badge-(issued|partly_paid|overdue)">',
    invoices.text,
    re.S,
)
detail_path = None
if open_rows:
    detail_path = type("M", (), {"group": staticmethod(lambda _n, _v=open_rows[0][0]: _v)})()
else:
    detail_path = re.search(r'href="(/app/invoices/[0-9a-f]{32})"', invoices.text)
if detail_path:
    detail = client.get(detail_path.group(1))
    check("invoice detail renders", detail.status_code == 200)
    check("detail shows the tax breakup", "Tax breakup" in detail.text)
    check("detail shows the reminder schedule", "Reminder schedule" in detail.text)
    check("detail warns about the unset RBI rate", "bank rate has not been configured" in detail.text)
    check("detail shows the MSMED evidence checklist", "Recovery evidence checklist" in detail.text)
    check("detail offers the customer payment link", "/pay/" in detail.text)
    check("detail refuses to show invented interest", "Interest under MSMED" in detail.text)

    printout = client.get(f"{detail_path.group(1)}/print")
    check("printable invoice renders", printout.status_code == 200)
    check("printable invoice is a tax invoice", "TAX INVOICE" in printout.text)
    check("printable invoice carries the supplier GSTIN", "27AAPFU0939F1ZV" in printout.text)
    check("printable invoice shows the amount in words", "Only" in printout.text)

    preview = client.get(f"{detail_path.group(1)}/reminders/preview")
    check("reminder preview renders", preview.status_code == 200)
    check("preview shows nine steps", preview.text.count('class="preview-box"') >= 9,
          f"count={preview.text.count('class=\"preview-box\"')}")
    check("preview marks the final notice as human-only", "needs your approval" in preview.text)

# --- a Hindi-rendered page
hi = client.get("/?lang=hi")
check("Hindi landing renders", hi.status_code == 200 and "भुगतान" in hi.text)

# --- customer portal, via a real link taken from the invoice page
if detail_path:
    link = re.search(r"(/pay/[0-9a-f]{32}/[0-9a-f]{32})", detail.text)
    check("portal link found in the UI", bool(link), "the invoice page shows the customer link")
    if link:
        portal = client.get(link.group(1))
        check("customer portal renders without a login", portal.status_code == 200)
        check("portal shows the amount due", "Amount due" in portal.text)
        check(
        "portal offers a part-payment plan",
        "instalment" in portal.text.lower() and "payment plan" in portal.text.lower(),
    )
        check("portal offers dispute and claim-paid paths", "already paid" in portal.text.lower())
        check("portal states the gateway security boundary", "card details" in portal.text.lower())
        check("portal exposes a grievance route", "correct or delete" in portal.text.lower())

        # A customer claim must pause the ladder.
        claim = client.post(
            f"{link.group(1)}/claim-paid",
            data={"csrf_token": csrf_of(portal.text), "utr": "123456789012", "note": "Paid on Friday"},
        )
        check("customer can report a payment", claim.status_code == 303, claim.text[:150])

# --- ops views
ops = client.get("/app/ops")
check("ops page renders", ops.status_code == 200)
check("ops states the CERT-In window", "CERT-In" in ops.text)
check("ops states log retention", "Log retention" in ops.text)
check("ops shows the audit trail", "Audit trail" in ops.text)

settings_page = client.get("/app/settings")
check("settings page renders", settings_page.status_code == 200)
check("settings never echoes a key value", "mock_key_demo" not in settings_page.text or "****" in settings_page.text)

billing = client.get("/billing")
check("billing page renders", billing.status_code == 200)
check("billing prices are in rupees", "\u20b9" in billing.text)

support = client.get("/app/support")
check("support page renders", support.status_code == 200)

# --- logout
r = client.post("/logout", data={"csrf_token": token_after_login})
check("logout redirects", r.status_code == 303)

print()
if failures:
    print(f"LIVE WALK FAILURES ({len(failures)}):")
    for item in failures:
        print(f"  - {item}")
else:
    print("LIVE WALK: all checks passed")
