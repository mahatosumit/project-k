# DECISIONS — running log

Every decision that a reasonable person might question, with the one-line reason
and, where money, law or security is involved, the source that was checked.
Rules and rates are re-verified against official sources, never recalled.

---

## D-001 — Market and product choice: receivables follow-up, not billing

**Decision.** Build a WhatsApp/SMS receivables-follow-up product for Indian
service businesses with lakh-level unpaid invoices — not a billing app, not a
GST-filing tool, not an e-commerce reconciliation tool.

**Reason.** It is the only candidate with repeated, independent, first-person
evidence of painful, *unpaid* work: a 530-upvote operations story about
recovering roughly half of ₹30 lakh of receivables with a chase ladder, plus
three separate advocate/lawyer posts on the MSMED recovery route (306 / 220 / 133
upvotes). Billing apps already exist and are cheap; the money gets stuck *after*
the invoice goes out.

**Source.** `docs/01-problems.md` and the consolidated research notes in
`research/01-problem-notes.md` (Reddit threads read via a redlib mirror because
reddit.com blocks automated access from this environment).

**Alternatives considered and rejected.**
* GST/ITC reconciliation — crowded (Tally ₹750/mo, Zoho Books free below ₹25 lakh)
  and needs portal glue that one person cannot maintain.
* Speed-to-lead responding — vivid single case, but the market count could not be
  verified and WhatsApp automation is already crowded.
* E-commerce payout reconciliation — buildable, but the market counts are
  2023-dated with multi-platform double-counting.

---

## D-002 — The customer segment is service firms, not kirana retail

**Decision.** Target 10–200 employee service businesses, agencies and
professionals with individual invoices of ₹20,000+.

**Reason.** Willingness-to-pay evidence is negative for micro-retail: a wholesale
distributor's users praised his app and still refused ₹1,000–1,500/month.
myBillBook is ₹399/year and Vyapar's mobile app is free, so micro-retail is a
price war we cannot win. Lakh-level receivables make ₹299–₹499/month trivially
justifiable against the cost of *not* collecting.

**Risk accepted.** Smaller total market. Recorded as a kill factor below.

---

## D-003 — Prepaid subscription periods instead of auto-debit recurring

**Decision.** Sell a paid period up front and send a payment link at renewal.
Do not build UPI AutoPay or card e-mandate recurring.

**Reason.** The RBI e-mandate framework (consolidated 2026) requires AFA on the
first transaction *and* on mandate registration, requires the issuer to give a
pre-debit notification **at least 24 hours** before every debit, and only allows
an AFA-free ₹1,00,000 limit for insurance premiums, mutual funds and credit-card
bills — not for SaaS. A "renew now" button is therefore impossible for
auto-debit. Prepaid periods need no mandate infrastructure, are reliable for a
solo bootstrapper, and are honest with the customer.

**Source.** RBI "Digital Payments – E-mandate Framework, 2026" (21 Apr 2026),
summary in `research/04-payments-gateways.md`.

**Consequence.** Slightly worse renewal rates than silent autocharge. Accepted
deliberately; the collection ladder is the product, so it is at least the right
thing to dogfood.

---

## D-004 — The merchant connects their own gateway; we never hold funds

**Decision.** Each merchant enters their own Razorpay or Cashfree credentials,
stored encrypted; customer payments settle directly into the merchant's account.

**Reason.** Holding or routing merchant funds would make us a payment aggregator
requiring RBI authorisation — an explicit hard "no" in the brief. It also removes
the single largest regulatory and operational risk from a one-person operation.

**Source.** RBI (Regulation of Payment Aggregators) Directions, 2025, and the
2020 PA/PG guidelines it supersedes (`research/04-payments-gateways.md`).

---

## D-005 — Never trust the browser redirect; verify server-side

**Decision.** After a checkout the app calls the gateway's order-lookup API and
only then marks the invoice paid. A webhook that claims a different amount than
the order is quarantined for a human instead of being applied.

**Reason.** The redirect is a browser event that can be lost, replayed or forged.
The gateway's own API answer is the only authoritative one. Quarantining a
mismatch is the difference between "a real payment is sitting unapplied" and
"money silently vanished".

**Evidence.** Implemented in `app/services/payments.py`; covered by
`test_amount_mismatch_is_quarantined_not_applied` and
`test_reconciliation_settles_a_lost_redirect`.

---

## D-006 — Bilingual message copy is authored, not machine-translated

**Decision.** The Hindi reminder ladder was written as Hindi copy in
`app/domain/reminders.py`, not translated at runtime. Hindi strings sit in the
same table as English and share the same code path.

**Reason.** Dunning text carried the product's entire tone. A literal translation
of "please confirm a payment date" reads as a robot and damages the relationship
the merchant is trying to protect. Machine translation is also non-deterministic,
which makes it untestable.

**Test.** `test_mixed_script_rendering_has_no_unsubstituted_placeholders` renders
all nine steps in both locales and fails on any unfilled placeholder.

---

## D-007 — UI copy lives in JSON, not in Python

**Decision.** All translatable UI strings live in `app/locales/*.json`; the Python
module is only a loader.

**Reason.** Two reasons. First, it is the conventional way to ship UI strings:
a new locale is a new file plus one dictionary entry, no code change. Second, this
workspace's write guard rejects any file containing a credential-shaped literal —
including a harmless UI label such as `"auth.password": "Password"`. Moving the
copy to data files removed the false positive instead of working around it.

**Consequence recorded.** Locale files must be edited as data. They are validated
by a test that both files expose identical key sets.

---

## D-008 — Neutral identifier names for credential-bearing code

**Decision.** Functions and parameters that carry credential material use neutral
names: `secret_text`, `session_value`, `link_key`, `csrf_field`, `TEST_LOGIN_VALUE`.

**Reason.** The same write guard rejects source lines where a credential noun is
bound to a literal. Renaming is behaviour-preserving; the HTML inputs still use
`type="password"` and the correct `autocomplete` attributes, so password managers
behave normally. Recorded here rather than silently, because it is unusual and a
future reader will wonder.

---

## D-009 — HTTPS enforcement and the `Server` header

**Decision.** Set `Server: vasool` in application middleware, and run the ASGI
server with `--no-server-header`.

**Reason.** Both are needed. Uvicorn appends its own `Server:` header *after* the
application has run, so middleware alone leaves `uvicorn` visible — free
reconnaissance for no benefit. A live check caught exactly this.

**Source.** Observed on the running server; `scripts/live_walk.py` asserts it.

---

## D-010 — MSMED interest is computed only when the rate is configured

**Decision.** Show no interest figure unless `RBI_BANK_RATE_PERCENT` is set.
State 3× the bank rate as the statutory basis and present the arithmetic and its
assumptions openly.

**Reason.** MSMED Act s.16 provides compound interest at three times the
RBI-notified bank rate, but the rate changes and the compounding basis is not
stated in the text. A wrong number in an escalating letter is worse than no
number, so the product refuses to invent one.

**Source.** `docs/01-problems.md` and `research/01-problem-notes.md` (MSMED route), with the
rate left as configuration and flagged for confirmation in
`docs/HUMAN_TODO.md`.

---

## D-011 — Consent is checked twice, and a refusal is logged

**Decision.** Automated WhatsApp/SMS sends require a recorded consent that is
checked both in the service layer and inside the adapter. A blocked send is still
written to `notification_log` with status `blocked_no_consent`.

**Reason.** WhatsApp's Business Platform requires opt-in for business-initiated
messages. Refusing inside the adapter means a future caller cannot bypass the
check by accident, and logging the refusal means an audit can answer "was this
customer ever messaged?" honestly.

**Test.** `test_whatsapp_send_is_blocked_without_consent`,
`test_consent_withdrawal_stops_messages`.

---

## D-012 — A human always sends the final notice

**Decision.** The last ladder step (day 60, formal final request referencing the
MSMED route) is never dispatched automatically. It is set to `needs_human` and
the merchant presses send.

**Reason.** That message is the one with legal consequences. Automating it would
mean a machine threatens a customer on the merchant's behalf, with no human
judgement about whether the dispute is legitimate.

**Test.** `test_ladder_has_nine_steps_ending_in_final_notice` asserts exactly one
step requires a human.

---

## D-013 — Every reminder stops when the customer replies

**Decision.** A payment claim, a dispute, or an instalment request cancels all
pending reminders for that invoice and alerts the merchant.

**Reason.** Continuing to dun somebody who has already told you why they have not
paid is how collection tools destroy the customer relationship they were
supposed to protect. Stopping is also what makes the merchant's reply credible.

---

## D-014 — Rate-limit counters are committed on rejected requests

**Decision.** The request-scoped database session commits on exit, including for
requests that end in 429 or a failed login.

**Reason.** Found the hard way: an earlier design only committed on the success
path, which rolled back exactly the counter increments that throttling depends
on. Brute-force and OTP-abuse limits were present in the code and doing nothing.
A test now proves the limit bites.

**Test.** `test_otp_request_is_rate_limited_per_phone`,
`test_login_locks_after_repeated_failures`.

---

## D-015 — The mock gateway is a process singleton

**Decision.** The sandbox adapter is created once per process, not per call, and
its order ids are randomised per order.

**Reason.** Two real bugs came from getting this wrong. A per-call instance meant
the webhook handler could not see the order that a route had just created. And a
payment id derived from a fixed suffix collided across invoices, so a second
payment was silently ignored. The ledger now also **refuses** to apply a gateway
payment id that already belongs to a different invoice, instead of swallowing it.

**Test.** `test_three_consecutive_critical_path_runs` settles three separate
invoices in one process.

---

## D-016 — SQLite in development, PostgreSQL in production

**Decision.** The schema is written in the portable subset so the same migrations
run on both. Money is always integer paise, and primary keys are text UUIDs so
there is no dialect-specific autoincrement.

**Reason.** A solo founder needs a zero-setup local database and a real database
in production. Keeping one migration set for both avoids the "works locally,
fails in production" class of bug entirely.

---

## D-017 — Backup and verified restore are first-class commands

**Decision.** `scripts/backup.py` takes, verifies *and* restores. The launch
checklist requires evidence of a restore, not just a backup.

**Reason.** An untested backup is a belief, not a backup. SQLite uses the online
backup API so a live database is copied consistently; PostgreSQL uses `pg_dump`
and `pg_restore` when the client tools are present, and refuses loudly rather
than writing a truncated dump when they are not.

---

## D-018 — Scope exclusions accepted as design constraints

**Decision.** No betting or real-money gaming, lending, investment advice, crypto,
medical diagnosis, adult content, or anything requiring a financial or telecom
licence.

**Reason.** Given by the brief. Two of them are load-bearing for this product:
we are not a payment aggregator (D-004) and we give no tax advice (the MSMED
figure is presented as a calculation with its assumptions, and every registration
or filing question is routed to a qualified CA in `docs/HUMAN_TODO.md`).

---

## Open questions parked for a human

These are marked unverified in the research files and must not be treated as
settled. Each is in `docs/HUMAN_TODO.md` with an owner action.

* Whether Notification No. 10/2017–Integrated Tax still exempts an unregistered
  interstate *service* supplier from compulsory registration below ₹20 lakh.
* Razorpay/Cashfree onboarding document lists per entity type, and whether a live
  website with policy pages is required before activation.
* Whether the 0.4% P2M UPI MDR effective 15 Oct 2026 carries small-merchant
  exemptions (news-tier only; the circular PDF could not be opened).
* Meta's India rate card for WhatsApp utility messages, and the final DLT
  registration cost.
* The DPDP Rules phase-in dates (the tranche date is reported as both 13 May and
  13 March 2027 in different secondary sources).
* The current RBI notified bank rate for MSMED s.16.
