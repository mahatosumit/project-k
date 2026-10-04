# 03 — Compliance map

Every row states the obligation, what the product actually does about it, and what
a human must still do. Sources are the official instruments, cited in
`research/03-gst-and-tax.md`, `research/04-payments-gateways.md` and
`research/05-dpdp-messaging-hosting.md`. **Nothing here is legal or tax advice.**

---

## 1. Payments

| Requirement | Source | Product does | Human must do |
|---|---|---|---|
| Not act as a payment aggregator without RBI authorisation | RBI (Regulation of Payment Aggregators) Directions, 2025 | Merchant connects their **own** gateway; money never touches us; no fund pooling | Confirm the chosen gateway's PA status is active |
| Support UPI, cards, netbanking, wallets | NPCI / gateway docs | Gateway-hosted checkout offers all of them; we integrate per method-agnostic | — |
| Card data must not be stored by the merchant | RBI / PCI-DSS | Hosted checkout only; no card field exists in our forms; only a gateway payment id is stored | Never introduce a card form later |
| Verify every payment server-side | Gateway docs | Webhook signature over the raw body **plus** a server-to-server order lookup; the browser redirect is never trusted | — |
| Webhook authenticity, replay and duplicate handling | Gateway docs | HMAC verification; unique `(provider, event_key)`; unique `(provider, gateway_payment_id)`; event ordering not assumed | Rotate the webhook signing key when it changes at the gateway |
| Idempotent payment handling | — | A `paid` order is never re-applied; a duplicate delivery returns 200 without a second credit | — |
| Daily reconciliation | — | `scripts/run_jobs.py` sweeps pending orders, re-asks the gateway, repairs the invoice cache from the payments table, and reports `paid_uncredited` items | Schedule the job (see the cron example in `deploy/`) |
| Refund flow | Gateway docs | Refunds are recorded (`refund_requested`) and surfaced; **not** automated, because money leaving the account must be deliberate | Execute refunds in the gateway dashboard; add the auto-refund API once live keys exist |
| E-mandate rules for recurring | RBI e-mandate framework (consolidated, 21 Apr 2026) | Recurring auto-debit deliberately **not** used: AFA on first charge, 24-hour pre-debit notice and the ₹1,00,000 no-AFA carve-out (insurance/MF/cards) do not suit SaaS | Renewals are manual/prepaid — see DECISIONS D-003 |

## 2. Tax and invoicing

| Requirement | Source | Product does | Human must do |
|---|---|---|---|
| GST registration threshold | CGST Act s.22 (₹20 lakh services) | Setting `gst_registered` is authoritative: when off, **no tax lines** are emitted, which is correct below the threshold | Decide and register; confirm whether inter-state exemption applies (UNVERIFIED — see HUMAN_TODO) |
| CGST+SGST vs IGST by place of supply | IGST Act s.12(2)(a) | Supplier state compared to place of supply; intra-state splits the rate in half, inter-state charges IGST; the total always foots to the components | Keep the supplier state correct in settings |
| Tax invoice contents | CGST Rules, Rule 46 | Supplier name/address/GSTIN, consecutive ≤16-character per-FY serial, date, recipient details, HSN/SAC, description, taxable value, rate, tax amounts, place of supply, reverse-charge flag, signature provision, and the unregistered-supplier declaration | Have an accountant review the template once |
| Time limit to issue | Rule 47 (30 days for services) | `issue_date` is recorded and shown; the product never backdates a serial | Issue invoices promptly |
| SAC code | CBIC classification | Default 998314 (IT design and development services), editable | Confirm the correct SAC for your services with a CA |
| E-invoicing (IRN/QR) | Notification 10/2023 (₹5 crore) | Not implemented, and not applicable below ₹5 crore aggregate turnover | Re-check if turnover approaches the threshold |
| GST returns and filing | GST portal | **Out of scope.** No returns are prepared or filed | Register, file GSTR-1/3B, engage a CA |
| Amount in words, Indian numbering | Rule 46 practice | Lakh/crore wording and Indian digit grouping (`₹1,23,456.78`) implemented and tested | — |

## 3. Data protection

| Requirement | Source | Product does | Human must do |
|---|---|---|---|
| Consent notice, itemised and standalone | DPDP Act 2023 s.5, Rules | Consent recorded with notice version, source, timestamp and evidence; withdrawal recorded and effective immediately; automated WhatsApp/SMS refuses without a current consent | Publish the notice; complete the lawyer review |
| Purpose limitation and minimal collection | DPDP Act 2023 | Collects only business/customer contact details and invoice amounts; **no Aadhaar, no customer PAN, no card data** | Do not add ID fields later without a legal need |
| Data-principal rights: access, correction, erasure | DPDP Act 2023 | Per-customer JSON export covering identity, consents, invoices, payments, reminders and disputes; erasure via a recorded request with a statutory due date; a 48-hour acknowledgement SLA surfaced in the ops view | Review the wording of the notice and the grievance route |
| Grievance officer | DPDP Act 2023 | Configurable per merchant, printed on the invoice, and available on the customer portal | Name a real person with working contact details before onboarding |
| Breach notification | DPDP Rules / CERT-In | Incident record with a computed reporting deadline; severity, scope, affected count and a resolution note | File within the deadline; the runbook is in `docs/OPERATIONS.md` |
| Phase-in dates | DPDP Rules 2025 (G.S.R. 846(E)) | Obligations are implemented now rather than when enforcement starts | Confirm the live dates (reported inconsistently — UNVERIFIED) |
| SPDI Rules (still live) | IT Act s.43A, G.S.R. 313(E) | Privacy policy, consent, grievance route and reasonable security practices in place | Annual review if following the ISO 27001 path |

## 4. Security incident reporting and logging

| Requirement | Source | Product does | Human must do |
|---|---|---|---|
| Report internet-facing incidents within 6 hours | CERT-In Direction No. 20(3)/2022-CERT-In, 28.04.2022 | Ops view states the window and auto-computes each incident's deadline; the incident runbook is in `docs/OPERATIONS.md` | Actually report to CERT-In; keep the reporting contact on file |
| Retain ICT logs 180 days, inside India | Same direction | Structured JSON logs with rotation; a maintenance job prunes audit rows past the retention window (default 180 days); `LOG_RETENTION_DAYS` and `CERT_IN_REPORT_HOURS` are configuration | Choose an India-region host and keep backups there |

## 5. Messaging and telecom

| Requirement | Source | Product does | Human must do |
|---|---|---|---|
| Register on DLT before sending commercial SMS | TRAI TCCCPR 2018 | The SMS adapter **refuses to send** unless the DLT entity id, sender header and template id are all configured | Complete DLT registration (entity, header, templates) |
| WhatsApp opt-in for business-initiated messages | WhatsApp Business Platform terms | Consent enforced twice; a refusal is logged; only utility-style transactional content is used, never marketing | Get a Business number and the sender approved; obtain and record opt-in |
| Template approval | Meta docs | The adapter supports template sends; the composed-text path is what runs today | Submit templates for the eventual production sender |
| No spam, no third-party messaging | TRAI / Meta | A message can only go to the address on the customer record, never to a value supplied in a request (review M1) | Use the product as intended |

## 6. Consumer-facing pages

| Requirement | Product does | Human must do |
|---|---|---|
| Privacy policy | Written, matching actual behaviour, versioned (`/legal/privacy`) | Lawyer review before first paying customer |
| Terms of service | Written, including the "not advice / not a payment aggregator" limits (`/legal/terms`) | Lawyer review |
| Refund and cancellation policy | Written, one-click cancellation, never removes a paid-for period (`/legal/refund`) | Confirm against the gateway's requirement list at onboarding |
| Contact and grievance | `/legal/grievance`, plus the per-merchant officer on invoices and the portal | Fill in the operator's own details on that page |
| Website required before gateway activation | Not a rule the product can satisfy for you | Publish this site on HTTPS with the four policy pages reachable |

---

## What is explicitly out of scope

The product gives **no tax, legal or investment advice**, does no lending or
credit scoring, holds no customer funds, files no returns, and prepares no
filings. The MSMED interest figure is presented as a calculation with its rate
and assumptions stated, and shows nothing at all until the RBI bank rate is
configured — precisely so that no user mistakes it for advice.
