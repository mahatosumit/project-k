# 03 — Product requirements (one page)

## Target user

**Primary:** the owner or the one accounts person at an Indian service business of
10–200 employees — an agency, a design or IT services firm, a consultancy, a
contract manufacturer's office — who has 10–200 open invoices and ₹5–50 lakh of
receivables, at least some of it more than 45 days old.

**Secondary:** the same loop at freelancer scale (smaller tickets, same workflow).

**Explicitly not:** micro-retail kirana (they will not pay this price — see
`docs/01-problems.md` §C), and any buyer needing credit, lending or investment
functionality.

## Job to be done

> "When I finish a job and raise an invoice, make sure I get paid on time without
> me having to chase it, and without me damaging the relationship by chasing it
> badly."

## The "aha" moment

The merchant sees the **reminder ladder preview** for a real invoice: nine dated
messages in Hindi or English, with the exact wording, ending in a formal notice
they will send themselves. The realisation is "I have not been doing this at all,
and I could not have written these messages." The second aha is a customer paying
through the portal link and the ladder stopping by itself.

## Must-have features (and nothing else)

1. **Phone-OTP or e-mail login**, and business profile with GST settings.
2. **Customers** with contact details, GSTIN and recorded WhatsApp consent.
3. **Invoices** with correct CGST/SGST/IGST, Rule 46 particulars, consecutive
   per-FY numbering, printable/PDF, and part payments, credits and write-offs.
4. **The reminder ladder** — nine steps over ~4 months, bilingual, previewable,
   resumable, idempotent, and stopping the moment the invoice is settled or the
   customer responds.
5. **Customer portal** reached by an unguessable per-invoice link, supporting pay,
   claim-already-paid, dispute and instalment request — each of which pauses the
   ladder and alerts the merchant.
6. **Merchant's own gateway** (Razorpay or Cashfree), signature-verified webhooks,
   server-side payment confirmation, idempotent settlement, daily reconciliation.
7. **MSMED evidence pack** and a running/past-due/recovery-stage view.
8. **Ops surface**: consent records, notification log, audit trail, data
   export/erasure, incident clock.

## Non-goals (deliberately cut)

* Inventory, stock, purchase orders, payroll, accounting reports.
* Filing GST returns or preparing tax documents.
* Holding or routing money; any lending, credit scoring or financing offer.
* Automatic legal notices. The product prepares documents; a human sends them.
* iOS/Android apps. It is an installable PWA.
* Anything in the brief's hard-no list: betting, lending, investment or trading
  advice, crypto, medical diagnosis, adult content, anything needing a financial
  or telecom licence.

## Pricing and packaging

Covered in `docs/02-validation.md` §4: ₹299/month or ₹2,999/year, fees in INR,
GST extra where applicable, 14-day free trial without a card. Prepaid periods —
no auto-debit (see DECISIONS D-003). A merchant's gateway fees are theirs, and we
never take a cut of the money owed.

## Metrics that decide whether this lives

| Metric | Definition | Target by week 4 | Target by week 12 |
|---|---|---|---|
| **Activation** | Signed up → issued ≥1 invoice with the ladder running | 60% | 70% |
| **Gateway connected** | Signed up → connected their own gateway | 30% | 50% |
| **Free → paid** | Trial → any paid period | 10% | 15% |
| **Customer response rate** | Invoices where the customer replied via the portal | 15% | 25% |
| **Recovery rate** | Overdue value collected within 60 days of becoming overdue | 40% | 55% |
| **Monthly churn** | Paid orgs cancelling | <8% | <5% |

**The one number that matters most** is recovery rate: if the ladder does not
visibly collect money, none of the others matter. Activation without recovery is
a licence sold to a wall.

## Dependencies that could invalidate this plan

1. Gateway merchant KYC — a human action, weeks of lead time.
2. WhatsApp template approval and DLT registration — a human action, and the
   ladder's primary channel.
3. Entity registration and a business bank account.
4. CA review of the MSMED interest presentation and the legal pages.

All four are in `docs/HUMAN_TODO.md` with time estimates. None of them blocks
building or testing, which is why the code is finished before any of them is done.
