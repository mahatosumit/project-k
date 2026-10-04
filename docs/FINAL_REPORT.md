# FINAL_REPORT

**Build date:** 2026-10-04
**Product:** Vasool — receivables follow-up for Indian service businesses
**Status:** software complete, tested, and green. **Not launched.** No live
payments, no real messages, no customers, no revenue.

---

## 1. What I built, and why

An India-only, self-hostable web app that chases unpaid invoices on a schedule,
takes payment through the merchant's own gateway, and produces a documented
recovery pack when a customer still will not pay.

The choice came out of the research, not a preference. Across the problems mined
from Indian forums and app-store reviews (`docs/01-problems.md`, 27 problems), the
only one with **repeated, independent, first-person evidence plus a documented
workaround that worked** was receivables follow-up: a 530-upvote operations story
recovered roughly half of ₹30 lakh with a chase ladder, and three separate
legal-community posts described the MSMED recovery route. Billing software is
cheap and everywhere (myBillBook ₹399/year, Vyapar free on mobile). The money gets
stuck *after* the invoice goes out, and nobody was selling the ladder.

**The product's load-bearing idea:** a machine should send the polite reminders,
and a human should send the one message with legal consequences. Every other
decision follows from that.

### What it does

* **The ladder:** nine touches across about four months, from a friendly nudge three
  days before the due date to a formal MSMED-aware final letter. Bilingual, with
  authored Hindi (not machine-translated), previewed in full before anything sends.
  Both the ladder's wording and its endings matter: it stops the moment the invoice
  is settled, or the customer disputes it, claims it is paid, or asks for
  instalments.
* **The customer portal:** reachable only by an unguessable per-invoice link, no
  login. The customer can pay, say "already paid", dispute the amount, or ask for a
  plan. Each response pauses the ladder and alerts the merchant.
* **Money:** the merchant connects their own Razorpay or Cashfree account, so
  customer payments settle into their account and never touch ours. Payments are
  confirmed through the gateway's own server-to-server lookup — the browser redirect
  is never trusted. Webhooks are signature-verified over the raw body, replay-proof,
  and idempotent.
* **The paperwork:** a recovery-stage view, an ageing panel, an MSMED interest
  calculation that shows its rate and assumptions, and a document checklist.

---

## 2. Evidence for the market gap

Summarised here, sourced in `docs/01-problems.md` §F:

* Unpaid-invoice pain recurs across **independent authors**, not one thread: an
  agency owner, a practising advocate, a wholesale distributor, a billing-software
  founder.
* A **workaround that demonstrably worked** (a dedicated e-mail alias, an escalation
  ladder, split-payment offers → more than half of ₹30 lakh recovered in six weeks).
  A working manual workaround is the strongest possible demand signal: it means
  someone is already paying in time.
* The **statutory lever exists and is public** (MSMED Act s.15 45-day payment, s.16
  compound interest at 3× the RBI bank rate) and small suppliers mostly do not use
  it, which is a gap software can close by preparing documents.
* **Competitors serve the wrong moment.** Billing apps remind once. WhatsApp
  automation tools are built for marketing. Foreign receivables tools assume cards,
  e-mail and Western prices.

**What I could not verify, and therefore do not claim:** total addressable market
(the service-firm share of GST registrations is an assumption), search demand (no
Trends data was collected), and — most importantly — that anyone will **pay** for
this. That is the first thing the pilot measures.

---

## 3. Pricing logic

₹299/month, ₹2,999/year, ₹5,999/year for multi-seat, 14-day free trial without a
card, GST extra where applicable.

Set against what Indian businesses already pay for adjacent tools — myBillBook
₹399/year, Vyapar desktop ₹3,099–3,399/year, TallyPrime ₹750/month — and against
the alternative: a part-time collections clerk costs many multiples of ₹299.

**The argument is not "cheaper than foreign software".** It is that recovering one
₹50,000 invoice pays for fourteen years of the annual plan. If a merchant does that
arithmetic unprompted, the price is right; if they do not, no discount fixes it.

**Deliberate choices:** no percentage of recovered money (that would make this a
debt-collection business with a different regulatory posture, and rewards the worst
relationships); prepaid periods rather than auto-debit, because the RBI e-mandate
framework needs AFA on the first charge and a 24-hour pre-debit notice, which rules
out the "renew right now" flow a small merchant expects.

---

## 4. Security and compliance posture

**Security.** 80 automated tests, ruff clean, bandit clean (0 issues in 7,573
lines), no advisories in the pinned dependency set, 0 hits in a secrets scan. An
independent adversarial review (`docs/security-review.md`) found 3 HIGH and 3
MEDIUM issues; all were fixed, each with a regression test. The three highs were
worth finding:

1. **Cross-tenant exposure on the ops dashboard** — any tenant could read every
   tenant's webhook payloads, audit trail and incident records. Fixed by adding
   `org_id` to the two models that lacked it and scoping every query.
2. **Money captured but never credited** — the order was marked paid *before* the
   ledger write, so a refused ledger entry made a real payment invisible with
   nothing retrying it. Fixed: money is now only marked paid once the ledger
   accepts it, and anything uncreditable is parked in a `paid_uncredited` state
   that the reconciliation sweep keeps surfacing.
3. **Double-credit race** — no database constraint on a gateway payment id, so a
   repeated delivery under a new event id could credit twice. Fixed with a unique
   index, because a check-then-insert is not a guarantee.

Two of my own bugs were the same class and are worth stating plainly: a **rate
limiter that did nothing** (the request session never committed, so counter writes
on rejected requests were rolled back) and **a real payment silently swallowed** by
an id collision. Both were found by tests written to check the thing actually
worked, not that the code looked right.

**Compliance** (`docs/03-compliance-map.md`, sourced in `research/`):
Payments are structured so the product is **not** a payment aggregator. GST is
split correctly (CGST/SGST intra-state, IGST inter-state), invoices carry the
Rule 46 particulars, and a non-registered supplier charges no tax. Consent is
recorded with notice version, source and timestamp, and sending refuses without it.
Data export and erasure are built in. The CERT-In 6-hour reporting deadline is
computed per incident and the runbook is written. SMS refuses to send without DLT
registration. The MSMED interest figure stays blank until the RBI rate is
configured, rather than guessing.

**The honest gap:** the policy pages were written to match the software but **no
lawyer has read them**, and several rules are marked UNVERIFIED because the
official sources could not be reached. Every one is in `docs/HUMAN_TODO.md`.

---

## 5. Known limitations

1. **No live payment has ever been processed.** Sandbox only. Switching is one
   configuration value, but merchant KYC is a human action.
2. **No message has ever been sent to a real person.** No DLT registration, no
   WhatsApp sender.
3. **No live HTTPS deployment.** Container, proxy and CI are written; no real host
   has run them.
4. **No PostgreSQL execution observed here.** Migrations are written portably and
   CI includes a PostgreSQL job, but the concurrency guarantee behind the
   double-credit fix has not been exercised on PostgreSQL.
5. **No visual or throttled-network verification.** Playwright could not be
   installed in this environment, so responsiveness on a low-end phone is unproven.
6. **No PWA manifest or service worker.** Deferred deliberately.
7. **The Cashfree webhook signature differs between their documentation and their
   own SDK** (`timestamp "." body` vs `timestamp body`). The adapter accepts either
   keyed form and records which matched, but which one the live service sends must
   be confirmed against sandbox traffic.
8. **Refunds are a recorded human action**, not automated.
9. **No customers, revenue, testimonials or reviews.** The landing page says so
   explicitly rather than inventing social proof.

---

## 6. Top five risks

| # | Risk | Why it could kill this | Mitigation / signal |
|---|---|---|---|
| 1 | **Nobody pays.** The strongest evidence collected was interest, not purchase. One prospect with the exact problem praised a tool and refused ₹1,000–1,500/month. | Fatal, and cheap to test | 20–30 conversations, pre-pay ₹499, kill if under 10%. Kill date already written down. |
| 2 | **Messaging rules or cost make the ladder uneconomic.** WhatsApp template approval and per-message cost are the product's main delivery channel, and both were unverifiable. | Fatal to the core loop | Submit templates early; keep e-mail plus portal as a fallback ladder; confirm the India rate card before promising pricing. |
| 3 | **Merchants will not connect their own gateway.** The whole "never touch the money" design depends on it. | Kills the payment half of the product | Measure the gateway-connection rate in the pilot; under 30% means re-thinking the model. |
| 4 | **Regulatory floor rises past a solo operator.** DPDP phase-in, CERT-In duties, GST registration. | Raises operating cost above a ₹299 price point | Narrow the segment if needed; all obligations are already implemented, so this is monitoring rather than building. |
| 5 | **Incumbent adds a ladder.** A billing app with distribution bolts on nine reminders. | Erodes differentiation | The moat is the customer reply path, the bilingual tone and the recovery pack, not the reminder count. Ship the answer to "what do I do when they still don't pay". |

---

## 7. The numbers that mean "keep going" versus "pivot or kill"

| Horizon | Keep going if | Pivot if | Kill if |
|---|---|---|---|
| **Week 1** | ≥5 of 20 outreach conversations booked, and at least 2 owners describe an invoice 45+ days old without prompting | Conversations happen but nobody names a specific stuck invoice | Under 2 conversations, or the problem is described as "not really an issue" |
| **Week 2** | ≥1 business pre-pays for a paid period before the product is finished; ≥30% of signups issue a real invoice | Signups happen but none issue an invoice (onboarding is the wall) | Zero signups from 40+ targeted touches |
| **Week 4** | ≥3 paying organisations, ≥1 has connected a gateway, ≥1 has collected a customer payment through it | Paying but not collecting: the ladder is not the problem they had | Under 3 payers after 20–30 conversations, or payers churn in month one |

**The single number that matters most is recovery rate:** overdue value collected
within 60 days of becoming overdue. Activation without recovery is a licence sold to
a wall. Target 40% by week 4, 55% by week 12.

---

## 8. Confidence rating, honestly

| Claim | Confidence | Why |
|---|---|---|
| The software works as designed and the critical path is correct | **High** | 80 tests including three consecutive end-to-end runs with signed webhooks; an independent review found and I fixed real defects; a live walk passes against a running server |
| The problem is real and painful | **High** | Repeated first-person evidence across independent authors, plus a workaround that worked |
| The chosen segment will pay ₹299–2,999 | **Low** | The decisive evidence does not exist yet. This is the whole point of the pilot |
| The market is big enough for a small business | **Medium-high** | Bottom-up arithmetic from citable counts supports it; the service-firm share is an assumption |
| The product is legally clear to launch | **Low-medium** | Obligations are implemented and sourced, but no lawyer has reviewed the pages and several rules remain UNVERIFIED |
| Unit economics work | **Low** | WhatsApp's India rate card and the post-October UPI MDR were not verifiable. Payment fees are known; messaging costs are not |

**Overall: high confidence that the engineering is sound, low confidence that the
business is. That asymmetry is deliberate** — the build was the part this
founder-engineer could control, so it was finished and tested properly, and the
uncertain part has been reduced to a small, cheap, time-boxed experiment with the
kill criteria written down before the conversations begin.

---

## 9. What I would do next, in order

1. **Talk to 20 Indian service-business owners** and ask one question: *what is the
   oldest invoice you are still waiting on, and what have you done about it?* Then
   ask for ₹499 up front. Nothing else in this list matters until that answer is in.
2. **Start entity registration and gateway KYC in parallel** — longest external
   lead time, and it blocks live money.
3. **Deploy to a real HTTPS host**, re-run `scripts/live_walk.py`, and hand a
   low-end Android phone to someone for an hour of real use.
4. **Submit WhatsApp templates and complete DLT registration.**
5. **Then, and only then, polish** — the PWA manifest, the second locale, automated
   refunds.
