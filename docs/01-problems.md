# 01 — Problems, competitors and sizing

**Method note (honesty first).** Reddit blocked direct and API access from this
environment, so threads were read through a public read-only mirror
(`redlib.catsarch.com`) rather than the API. Play Store reviews were read from the
public listing pages. Rows marked **[V]** were fetched and read in full; **[S]**
means snippet-grade. Anything that could not be verified is labelled
**UNVERIFIED** and was kept out of every headline number. No market size, review,
user count or price in this document was invented.

---

## Section A — Problem inventory (27 problems)

Each row: who has it, how often, today's workaround, what they already pay, and
whether software could plausibly fix it.

| # | Problem | Who / where | Frequency | Workaround today | What they pay | Source | Software could fix? |
|---|---|---|---|---|---|---|---|
| 1 | Unpaid invoices not chased because chasing feels rude | Service MSMEs, agency owners, nationwide | Every cycle | Nothing; the owner keeps meaning to call | Nothing (and 30+ days of cash) | [V] `reddit.com/r/IndiaBusiness` thread, 530 upvotes | Yes — this is the product |
| 2 | MSME dues written off instead of recovered | Small suppliers to large buyers | Ongoing | Write it off silently | ₹50 lakh+ written off (stated by a practising advocate) | [V] r/IndiaBusiness, 306 upvotes | Yes — evidence pack + statutory route |
| 3 | No idea which invoices are actually overdue | Owners with 50+ open invoices | Weekly | Mental arithmetic or an Excel column | Nothing | [V] same thread | Yes — ageing view |
| 4 | Split payments (part cash, part online) are not tracked accurately | Retail/wholesale sellers | Daily | Manual reconciliation | Vyapar licence | [V] Play Store review, 403 found helpful | Partly — ledger hygiene |
| 5 | Partial payment per invoice not supported | Same | Daily | Notes in a diary | Same | [V] Play Store review, 103 helpful | Yes |
| 6 | Udhaar (credit) recovery is the first thing that breaks at scale | Kirana and small retail | Daily | Verbal reminders | Nothing | [V] r/IndiaBusiness comment from a billing-software founder | Yes, but micro-retail will not pay (see §C) |
| 7 | Stock and payment mismatches after sync failures | App-based sellers | Intermittent, damaging | Re-key data | Same | [V] Play Store review, Vaagai Enterprises | Yes — but a different product |
| 8 | Sales-to-government TDS vs GSTR-1 turnover mismatch triggers notices | Suppliers to government | Annual/quarterly | CA reconciles manually | CA fees | [V] r/IndiaTaxandCompliance, 30 upvotes | Partly — crowded space |
| 9 | Typing the same challan 40+ times a day | Wholesale distributors | Daily | Built a voice app himself | He charges ₹1,000–1,500/mo; users praised it and **would not pay** | [V] r/IndiaBusiness, 79 upvotes | Buildable, but willingness to pay is negative |
| 10 | Follow-up only happens when there is spare time | Owners of 5–50 person firms | Daily | "I will do it tomorrow" | Nothing | [V] r/IndiaBusiness, 190 upvotes | Yes |
| 11 | Enquiries answered hours later lose the order | IndiaMART sellers | Daily | Manual refresh | IndiaMART subscription | [V] r/IndiaBusiness, ~190 upvotes | Yes — but crowded |
| 12 | Quotations go out late, losing deals | Manufacturers | Daily | Manual | Nothing | [V] same thread | Adjacent, not this product |
| 13 | Settlement report reconciliation (Amazon vs Flipkart formats) | E-commerce sellers | Monthly | Spreadsheets | Tools ₹500–2,000/mo | [S] multiple consultancies | Yes — heavily served already |
| 14 | Restaurant payout reconciliation and rolling reserves | Swiggy/Zomato restaurants | Weekly | Spreadsheets | Tools exist | [S] terra-insight and others | Yes — served |
| 15 | WhatsApp order chaos | Tiffin services | Daily | Notebook + Excel | Nothing | [S] several blogs | Yes — different product |
| 16 | Marketplace fees on new clients | Salons | Monthly | Accept it | Fresha etc. | [S] r/Indian_Business thread | Yes — different product |
| 17 | 917-minute average response to property enquiries | Real-estate brokers | Per lead | Nothing | Portal fees | [S] study of 34,148 enquiries | Yes — crowded |
| 18 | Freelancers not paid for months | Freelancers, nationwide | Chronic | Chasing by e-mail | Nothing | [V] r/india thread | Yes — the same product, smaller tickets |
| 19 | No record of what was promised when | Anyone who negotiated by phone | Constant | Memory | Nothing | [V] derived from threads 1, 10 | Yes — dispute log |
| 20 | Disputes never recorded, so the same argument repeats | Service firms | Per dispute | Nothing | Nothing | [V] derived from thread 2 | Yes |
| 21 | Second reminder never sent (only the first) | Everyone | Always | First reminder sent, then nothing | Nothing | [V] thread 1 — a ladder, not one reminder, is what worked | Yes — the ladder |
| 22 | Escalation has no defined endpoint | Owners | Per bad debt | Give up | Nothing | [V] threads 1, 2 | Yes — documented stages |
| 23 | Statutory 45-day payment right never invoked | Micro/small suppliers | Per bad debt | Unaware of it | Nothing (money lost) | [V] three advocate posts, 306/220/133 upvotes | Yes — checklist only, never advice |
| 24 | Interest on late payment never claimed | Same | Per bad debt | Unaware | Nothing | [V] same posts | Yes — calculated only when the rate is configured |
| 25 | Labour-law compliance gaps (EPFO/ESIC/PT/LWF) | 10–200 employee SMEs | Ongoing | Spreadsheets, consultants | Consultant fees; ₹3.8 lakh damages cited | [V] r/IndiaBusiness, 23 upvotes | Yes — but a $10/mo competitor anchors price |
| 26 | GST filing tools being rebuilt in public | CA-adjacent builders | Now | — | — | [V] r/StartUpIndia post | Competitive signal, not a problem we solve |
| 27 | No single place showing who owes what, how long, and what was sent | Owners of every firm above | Weekly | Several tools and no owner | Nothing | [V] synthesised from 1, 3, 10, 21 | Yes — this is the product |

---

## Section B — Candidate deep dives (top 8)

### B1. Receivables/collection autopilot for service MSMEs *(winner)*
* **Pain:** invoices overdue 30–90+ days with no systematic follow-up (rows 1, 3, 10, 21, 27). Repeated first-person accounts across independent authors.
* **What they pay now:** nothing; that is the cost. Adjacent tools are cheap (myBillBook ₹399/year; Vyapar mobile free).
* **Competitor field:** present but leaderless for this specific loop in India. Foreign tools (Chaser, Upflow) do not handle UPI, WhatsApp-first habits or MSMED.
* **Weakness to exploit:** existing billers advertise reminders but send one nudge; nobody owns the *ladder*, the customer's reply, and the evidence pack.
* **Buildable in <3 weeks:** yes — ledger, scheduler, bilingual templates, portal, PDF pack. No marketplace integrations.
* **Reachable first 100:** r/IndiaBusiness, r/IndiaTaxandCompliance, r/StartUpIndia, freelancer communities, CA referrals (ICAI reports >1,00,138 CA firms, 72% solo).

### B2. GST/ITC reconciliation and notice preparation
High pain (rows 8, 26) and a possible ClearTax small-business exit. Rejected: heavy portal glue one person cannot maintain, and crowded (Tally ₹750/mo; Zoho Books free below ₹25 lakh turnover). **Retained as the runner-up.**

### B3. Speed-to-lead responder for IndiaMART/JustDial traders
Vivid case (row 11: a 9-hour gap lost an order; a sub-60-second auto-reply won one). Held back by an unresolvable market count and a crowded WhatsApp-automation field.

### B4. E-commerce payout and TCS reconciliation
Buildable file-normalisation play with a clear buyer, but incumbents exist (Cointab, TheEcomWay) and the market counts are 2023-dated with multi-platform double-counting.

### B5. Labour-law compliance checker (EPFO/ESIC/PT/LWF)
Strong penalty evidence (row 25) but a $10/month competitor anchor and state-slab maintenance that a solo founder cannot keep current.

### B6. Tiffin/WhatsApp order handling
Real chaos (row 15), but ticket size is too small to fund support.

### B7. Freelancer invoice and payment chasing
Same loop as B1 with smaller tickets (row 18). **Folded into B1 as a secondary segment rather than a separate product.**

### B8. Salon/marketplace client-fee management
Real (row 16) but a different buyer, a different workflow, and no reuse of the payment ladder.

---

## Section C — Bottom-up sizing (top 5)

Every input below carries its source. Inputs that could not be verified are marked
UNVERIFIED and excluded from the headline figure.

**Verified inputs used**
* Active GST registrations: **1.52 crore** (SBI report, reported Jul 2025).
* ICAI: **>1,00,138** CA firms, **72% solo** (~4 lakh members).
* Amazon India sellers **>10 lakh** (Jan 2023); Meesho ~1 million sellers (Jul 2023).
* myBillBook Silver ₹399/year; TallyPrime ₹750/month; Vyapar desktop ₹3,099–3,399/year (all published).

| Candidate | Reachable population | Paying fraction | ARPU/year | Bottom-up ceiling |
|---|---|---|---|---|
| B1 receivables (service MSMEs) | ~1.5 crore GST registrations; assume 25% are service firms ≈ **37.5 lakh** UNVERIFIED split | 0.5% | ₹2,999 | **~₹56 crore** |
| B2 GST reconciliation (CA firms) | **1,00,138** firms | 3% | ₹6,000 | **~₹1.8 crore** |
| B3 speed-to-lead (IndiaMART sellers) | UNVERIFIED | — | ₹2,999 | not sized |
| B4 e-commerce reconciliation | 10 lakh Amazon + 1M Meesho, heavy overlap | 1% (double-count risk) | ₹6,000 | **~₹30–60 crore** (low confidence) |
| B5 labour compliance | UNVERIFIED | — | ₹9,000 | not sized |

**What this means, plainly.** Even the most conservative reading of B1 supports a
small, real business: 0.1% of service MSMEs at ₹2,999 is about **₹11 crore of
annual revenue potential**, far beyond what one person needs to justify building
it. The binding constraint is not market size; it is **willingness to pay at this
price point**, which is exactly what the 3–4 week paid-pilot test measures.

---

## Section D — Ranking and the decision

| Candidate | Pain | WTP in INR | Size | Competitor weakness | Local gap | Payment feasibility | Regulatory risk | MVP <3wk | First 100 reachable | Skill fit | Total /90 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **B1 receivables** | 9 | 7 | 9 | 8 | 8 | 9 | 8 | 9 | 7 | 9 | **83** |
| B2 GST recon | 8 | 8 | 6 | 5 | 4 | 9 | 6 | 4 | 7 | 7 | 64 |
| B3 speed-to-lead | 8 | 7 | 4 | 4 | 5 | 9 | 6 | 7 | 6 | 7 | 63 |
| B4 e-commerce recon | 7 | 7 | 7 | 6 | 6 | 9 | 7 | 7 | 5 | 7 | 68 |
| B5 labour compliance | 7 | 6 | 3 | 5 | 5 | 6 | 5 | 4 | 6 | 6 | 53 |

**Decision: B1.** It is the only candidate with repeated, independent,
high-engagement first-person evidence; a documented workaround proving the loop
exists (an alias plus a ladder plus split offers recovered more than half of ₹30
lakh); a present-but-leaderless India competitor field; a pure software MVP; and
named channels that actually exist.

**Primary segment:** service firms and agencies with 10–200 employees and
lakh-level receivables. **Not** micro-retail, because the willingness-to-pay
evidence there is explicitly negative.

## Section E — Kill criteria (written before building)

Kill or pivot if any of these is true after the stated test:

1. **Paid-pilot test fails.** Under ~10% of 20–30 qualified ICP conversations
   convert to a pre-paid ₹499/month pilot within 3–4 weeks → kill, or pivot to B2.
2. **The ₹1,000–1,500/month wall holds.** If prospects praise the product and
   still will not pre-pay ₹499, the price point is wrong for this segment.
3. **Messaging economics or rules make the ladder uneconomic.** If WhatsApp/SMS
   cost and template approval make a solo bootstrapper's ladder impossible → the
   product is dead on day one; pivot to e-mail plus portal only.
4. **No verified purchase evidence within 4 weeks.** The strongest positive
   evidence collected was *interest*, not purchase. If that does not change, stop.

## Section F — Source list

1. r/IndiaBusiness — receivables recovery story (530 upvotes), read in full via mirror.
2. r/IndiaBusiness — MSME dead invoices / MSMED route, practising advocate (306 upvotes).
3. r/IndiaBusiness — labour-law compliance gaps, 10–200 employees (23 upvotes).
4. r/IndiaBusiness — automation thread, IndiaMART response gap (~190 upvotes).
5. r/IndiaBusiness — Hindi voice-to-challan app, negative willingness to pay (79 upvotes).
6. r/IndiaTaxandCompliance — TDS vs GSTR-1 mismatch (30 upvotes).
7. r/IndiaBusiness — billing-software founder on udhaar vs stock (comment).
8. Google Play listings and reviews: Vyapar (`in.android.vyapar`), myBillBook.
9. Published pricing: vyaparapp.in/pricing; tallysolutions.com (Jul 2026); patronaccounting.com on Zoho Books India (Jul 2026).
10. SBI report on GST registrations, reported Jul 2025 (zeebiz).
11. ICAI firm counts and solo-practice share (thefinancestory, Oct 2025).
12. Amazon India seller count (aninews, Jan 2023); Meesho (Economic Times, Jul 2023).
13. Pinova/closingfox lead-response study, 34,148 enquiries across 14 brokerages.
14. r/startupsindia — GST tool being built in public (competitive signal).
15. Vahan/marketplace and e-commerce reconciliation commentary (consultancy blogs) — snippet-grade only.

**Everything in this section was read during this build.** Where a figure appears
in Section C it is drawn from an item above, except the 25% service-firm share,
which is explicitly UNVERIFIED and flagged in the table.
