# 03 — Threat model

Scope: the Vasool application (multi-tenant SaaS), its database, its gateway
integrations, its messaging paths, and the customer-facing payment portal.
Written as a design constraint, and revisited after the independent review in
`docs/security-review.md`.

---

## Assets, in order of what an attacker wants most

| Asset | Why it matters | Where it lives |
|---|---|---|
| **Money in transit** | Direct theft or fraud | Gateway orders, webhook endpoints, invoice totals |
| **Merchant gateway credentials** | Full control of a merchant's payment account | `organizations.gateway_key_secret_enc` (encrypted) |
| **Customer personal data** | Names, phones, e-mails, invoice amounts; DPDP obligations | `customers`, `invoices`, `notification_log` |
| **Merchant business data** | Who owes whom, and how much | All tenant tables |
| **Session and CSRF material** | Account takeover | Signed cookies |
| **Audit trail** | The ability to investigate anything | `audit_log`, `payment_events` |
| **Messaging capacity** | Abuse, cost, sender reputation | OTP and reminder send paths |

## Attackers, and what each actually wants

1. **A fraudulent customer** holding a legitimate portal link — wants a
   "payment recorded" state without paying.
2. **A competing or curious tenant** — wants another merchant's customer list or
   receivable book.
3. **An unauthenticated internet attacker** — wants account takeover, data, or
   free compute.
4. **An insider or careless operator** — misconfiguration, over-broad access.
5. **The merchant themselves, accidentally** — writing off money, sending a
   message to the wrong person, exporting data carelessly.

---

## Top abuse cases and the control for each

| # | Abuse case | Control (where it lives) |
|---|---|---|
| 1 | **Forged payment webhook**: attacker posts a fake "payment captured" | HMAC over the **raw** body verified before parsing (`app/adapters/payments.py`); invalid signatures recorded and refused; per-IP rate limit on the endpoint |
| 2 | **Replayed webhook**: same delivery repeated to double-credit | Unique `(provider, event_key)`; a `paid` order is never re-applied; **unique `(provider, gateway_payment_id)` index** so a second insert is impossible even with a new event id |
| 3 | **Amount tampering**: webhook claims a bigger/smaller amount than the order | Confirmed amount compared to the order; a mismatch is quarantined as `amount_mismatch` and never applied |
| 4 | **Redirect forgery**: customer returns from checkout claiming success | Nothing in the return URL is trusted; settlement requires the webhook plus a server-to-server order lookup |
| 5 | **Lost confirmation**: payment succeeds, redirect and webhook both fail | Daily reconciliation re-asks the gateway and settles; plus an opportunistic re-check on the callback page |
| 6 | **Money captured but uncreditable** (settled invoice, overpayment) | Order left as `paid_uncredited`, audited, and included in the reconciliation sweep — money cannot disappear silently (review H2) |
| 7 | **Portal link guessing** | 32-character HMAC derived from the customer key and the invoice id; compared with `compare_digest`; wrong/short is a plain 404 |
| 8 | **Cross-invoice link reuse** | The link token is per-invoice, so one invoice's link cannot be edited into another's |
| 9 | **OTP brute force** | Per-phone and per-IP hourly caps, 5 attempts per code, newest code invalidates older ones, codes stored HMAC-hashed |
| 10 | **SMS pumping / OTP flooding** | Rate limits consumed **before** the account lookup, so unknown numbers are throttled too (review fix); request-size limits; global per-IP ceiling |
| 11 | **Account enumeration** | Identical response and error for unknown account vs wrong credential, and for known vs unknown phone on OTP request |
| 12 | **Credential stuffing** | Per-IP login limit, per-account lockout after repeated failures, argon2id hashing, timing-safe comparison |
| 13 | **Session forgery / fixation** | Signed cookie bound to the credential hash; a password change invalidates all sessions; CSRF token rotated on every successful login |
| 14 | **CSRF on state-changing actions** | `verify_csrf` on every unsafe method; the check is centralised so a route cannot silently opt out |
| 15 | **Cross-tenant read/write** | Every tenant query filtered by `org_id` or 404; asserted route by route (dashboard, customers, invoices, print, export, write-off, ops). The ops page leak found in review is fixed and regression-tested |
| 16 | **Cross-org settlement via the sandbox path** | Order scoped to the caller's organisation before completion; sandbox routes refuse in production (review M3, M2) |
| 17 | **Unconsented messaging** | Consent recorded per customer and checked twice — in the service layer and inside the adapter; a refused send is still logged; the support acknowledgement can only use the address on the customer record, never a form value (review M1) |
| 18 | **Gateway credential theft from the database** | Encrypted at rest with Fernet; decrypted only at the point of use; displayed only masked; never written into audit detail |
| 19 | **Credential leak into logs** | The audit logger redacts credential-shaped keys and masks phones, e-mails and long digit runs; a test asserts the settings page never echoes a saved key |
| 20 | **SQL injection** | All access through SQLAlchemy parameter binding; no string-built SQL anywhere in `app/` |
| 21 | **XSS / stored XSS** | Jinja autoescaping on; no `|safe` on user data; input sanitisation strips control characters and tag-like sequences; CSP with no inline script |
| 22 | **Clickjacking, MIME sniffing, referrer leakage** | `X-Frame-Options: DENY`, `nosniff`, referrer policy, permissions policy, HSTS in production |
| 23 | **Framework fingerprinting** | `Server: vasool` in middleware plus `--no-server-header` on the ASGI server (both needed — the server re-adds its own header otherwise) |
| 24 | **Resource exhaustion** | 1 MiB request-body limit, per-IP global rate limit, bounded list limits, reminder dispatch batched, reconciliation capped per run |
| 25 | **Unbounded reminder sending** | Ladder rows are pre-scheduled and unique per step; only one transition to `sent`; a settled invoice cancels pending steps |
| 26 | **Dispute used as an attack** (spam disputes to stop all chasing) | Disputes pause the ladder **and** raise a merchant alert with a response deadline, so abuse is visible rather than silent |
| 27 | **Data-subject abuse** (export used to exfiltrate) | Exports are org-scoped, audited, and return `no-store`; the route 404s for another org's customer |
| 28 | **Insider/operator over-reach** | Audit log on every administrative action; tenant views org-scoped; the platform-wide reconciliation sweep is only reachable from the scheduler, not the tenant UI |

---

## Compliance-relevant controls

| Area | Control |
|---|---|
| **Payments (RBI/NPCI)** | Not a payment aggregator: the merchant's own gateway holds the money. Card data never reaches our servers (hosted checkout only). Payment confirmed through the gateway's API, not the browser. |
| **Payment data storage** | No card numbers, CVVs or bank credentials stored; only a gateway payment id and reference. |
| **GST** | Correct CGST/SGST vs IGST split by state; Rule 46 particulars on the printed invoice; 16-character per-FY numbering; no tax lines from an unregistered supplier. |
| **DPDP Act 2023** | Consent recorded with notice version, source and timestamp, and revocable; export and erasure built into the product; minimal collection (no Aadhaar, no customer PAN); grievance officer configurable per merchant. |
| **CERT-In directions** | Incident record with the 6-hour reporting deadline surfaced in the ops view; structured JSON logs; 180-day retention enforced by the maintenance job; logs remain inside the deployment host's jurisdiction. |
| **Messaging (TRAI / Meta)** | SMS refused unless the DLT entity, header and template ids are configured; WhatsApp sends refused without recorded consent. |

---

## Accepted risks (with the reason, so they are decisions and not oversights)

1. **A single-tenant compromise is possible if the app server is fully compromised.**
   Standard for this architecture; mitigation is the hardening in
   `docs/05-launch-checklist.md` plus database-level encryption on the host.
2. **No hardware MFA for merchant accounts.** Phone OTP is available; TOTP is not
   built, because Indian small-business users largely will not use it and support
   cost would exceed the risk for a ₹299/month product.
3. **WhatsApp delivery depends on Meta's template approval** for the eventual
   production sender; until then the ladder falls back to the configured channel.
4. **Refunds are a documented human action**, not automated (review L3), because
   money leaving the merchant's account must be deliberate.
