# 02 — Validation and the decision record

**Verdict: build it, with an explicit kill date.** This document records what was
validated, what could not be validated, and the criteria that will end the attempt.

---

## 1. What was actually verified, and what was not

**Verified with a citable source** (see `docs/01-problems.md` §F):
* Repeated first-person accounts of unpaid-invoice pain across independent authors.
* A documented workaround that worked: a dedicated e-mail alias, an escalation
  ladder and split-payment offers recovered more than half of ₹30 lakh.
* Three independent legal-community posts on the MSMED recovery route.
* Published competitor prices: myBillBook ₹399/year, Vyapar desktop ₹3,099–3,399/year,
  TallyPrime ₹750/month.
* Market counts for GST registrations, CA firms, Amazon and Meesho sellers.

**NOT verified — treat as risk, not fact:**
* **Nobody has ever paid for this product.** The strongest positive evidence in the
  research is *interest* plus a consultant's story where no software was sold.
* **No search-demand data was captured.** Google Trends volume was not collected,
  so keyword demand is unknown.
* The service-firm share of GST registrations (25%) is an assumption, not a
  measured figure.
* Whether the 0.4% P2M UPI MDR effective 15 October 2026 exempts small merchants.
* Razorpay/Cashfree onboarding document lists per entity type.

**Access caveat.** Reddit blocked direct access, so threads were read via a
public read-only mirror. Where a thread could not be read in full it is marked
snippet-grade in `docs/01-problems.md`. No review, testimonial, user count or
revenue figure anywhere in this project was invented.

---

## 2. Competitive landscape (what already exists)

| Segment | Incumbents | Their price | Where they leave a gap |
|---|---|---|---|
| Billing with basic reminders | Vyapar, myBillBook, Busy, Marg | ₹399/year to ₹9,000 one-time | One reminder, not a ladder; no customer reply path; no evidence pack |
| Accounting suites | Tally, Zoho Books | ₹750/month; Zoho free below ₹25 lakh turnover | Not designed around chasing; no WhatsApp-first flow |
| Foreign receivables tools | Chaser, Upflow, Growfin | $30–$200+/month | No UPI, no WhatsApp-first habit, no MSMED, price 10×+ local willingness to pay |
| WhatsApp automation | WhatZCRM, Practicestacks, Sprio | ₹500–3,000/month | Built for marketing/support, not money owed |

**The gap is specific and defensible for a small player:** an India-priced,
Hindi/English, WhatsApp-first *collection ladder* that (a) stops the instant the
customer replies, (b) takes payment through the merchant's own gateway, and (c)
produces a documented recovery pack. Every incumbent does part of this; none of
them treats the ladder as the product.

---

## 3. Positioning

> For Indian service businesses owed lakhs by their own customers: Vasool chases
> the money politely and relentlessly in Hindi or English, so you do not have to
> have the awkward conversation, and it hands you the paperwork if the customer
> still will not pay.

**What we are not:** not billing software, not a collections agency, not a
payment aggregator, not tax advice. Every one of those is stated on the landing
page, because being mistaken for them is a support and compliance cost.

---

## 4. Pricing logic, in rupees

| Plan | Price | Why this number |
|---|---|---|
| Free trial | ₹0, 14 days | Trust is the bottleneck; no card needed |
| Starter monthly | ₹299/month | Below the ₹399/year first-year anchor of myBillBook's paid tier but above "toy" pricing |
| Starter annual | ₹2,999/year (≈₹250/month) | Beats Tally's ₹750/month by 3× and offers two months free |
| Growth annual | ₹5,999/year | For 5+ staff; still one fifth of a part-time collections clerk's monthly cost |

**The pricing argument is not "cheaper than foreign software".** It is that
recovering **one** ₹50,000 invoice pays for fourteen years of the annual plan. The
test is whether a business owner does that arithmetic unprompted — which is
precisely what the pilot conversations measure.

**What we deliberately do not do:** take a percentage of recovered money. That
would make us a debt-collection business with a different regulatory posture, and
it perversely rewards the worst customer relationships.

---

## 5. Threat to the plan, and the kill criteria

| Risk | Signal to watch | Response |
|---|---|---|
| Willingness to pay is lower than evidence suggests | Under 10% of 20–30 qualified conversations pre-pay ₹499 | Kill or pivot to the runner-up (GST reconciliation) |
| WhatsApp/SMS template approval or cost blocks the ladder | Cannot get utility templates approved, or per-message cost makes a ladder uneconomic | Pivot to e-mail + portal ladder only |
| Merchants will not connect their own gateway | Under 30% complete gateway connection during the pilot | Re-think the model; this is the load-bearing assumption of D-004 |
| Regulatory change raises the compliance floor | DPDP Rules phase-in adds obligations a solo operator cannot meet | Narrow to a segment with fewer data subjects, or pause |

**Kill date: 4 weeks after the first 20 conversations.** Written here, before
those conversations, so the decision cannot be rationalised later.

---

## 6. What would make this a clear yes

1. 3+ businesses pre-pay for a paid period before the product is fully finished.
2. At least one merchant connects their own gateway and takes a real customer
   payment through it.
3. A merchant asks for a feature that deepens the loop rather than widening it
   (for example, "can it also chase my purchase orders?").
4. A CA or accountant asks to refer clients — the highest-signal distribution
   evidence available in this market.
