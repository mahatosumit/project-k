# Independent security review — 2026-10-04

Performed by a separate adversarial reviewer that was given the codebase and told to
find exploitable defects, not to praise the design. Every finding below was traced
to a file and function, then **fixed**, with a regression test added. This document
records what was found and what was done about it, so a future reader can see the
weaknesses the product has already had.

**Outcome:** 0 critical, 3 high, 3 medium, 4 low found → all highs and mediums
fixed and covered by tests. The lows are fixed or explicitly accepted below.

**Test evidence:** `python -m pytest tests -q` → **80 passed**, of which 12 are
regressions written specifically for the findings in this document
(`tests/test_security_fixes.py`).

---

## Method and coverage

Adversarial read of the whole request path — route → dependency → service → domain
→ adapter → model — plus the middleware stack and templates, in two passes.

Deliberately **not** repeated, because they were already run and were clean:
`ruff` (all checks passed), `bandit` (0 issues in 7,573 lines), a secrets pattern
scan over the repository (0 hits), and an OSV advisory check over the pinned
dependency set (0 advisories). Static tools cannot see authorisation logic or
money arithmetic, which is where the findings were.

---

## Critical

None found.

---

## High

### H1 — Cross-tenant exposure on the ops dashboard
**Location:** `app/web/routes/admin.py`, `ops_page()`; model gap in `app/models.py`
(`PaymentEvent`, `BreachEvent`).

**What was wrong:** the ops page was gated only by "is somebody logged in", and
its queries were unscoped. `PaymentEvent` (raw gateway payloads, containing payer
identifiers) and `BreachEvent` had no `org_id` column at all, and the
`AuditLog` / `DataRequest` / 7-day notification count queries did not filter by
the caller's organisation. `run_reconcile` from the UI also invoked the
platform-wide sweep.

**Exploit:** any authenticated user of any tenant opens `/app/ops` and reads every
other tenant's webhook payloads, audit trail, data-subject requests and incident
records; they could also trigger reconciliation across all organisations.

**Fix:**
* `org_id` added to `payment_events` and `breach_events` (migration `0002`).
* Every list on the ops page filtered by `org.id`.
* The in-app reconciliation button scoped to `org_id`; the unscoped sweep is only
  reachable from the scheduler.
* Incidents recorded from the UI carry the recording organisation.

**Regression:** `test_ops_view_does_not_leak_another_tenants_data`,
`test_payment_event_carries_the_owning_org`.

### H2 — Money captured but never credited, with no path back
**Location:** `app/services/payments.py`, `_settle()`.

**What was wrong:** the order was marked `paid` *before* the ledger write. If
`ledger.record_payment` then refused the payment (invoice already settled, or an
amount above the balance), the code audited a conflict and returned — but the
order was now `paid`, so it no longer matched the reconciliation sweep's status
set. The comment claimed the money was "recorded against the customer as credit";
no `apply_credit` call existed on that path.

**Exploit/failure:** customer pays → webhook verified → ledger refuses → money is
captured at the gateway, the invoice stays unpaid, nothing retries it, and no
operator queue shows it. Silent, undetectable revenue loss.

**Fix:** the order is no longer marked paid before the ledger accepts it. A refused
payment sets status `paid_uncredited`, stores the unapplied amount, payment id and
reason in the order notes, and is audited as `payment.uncredited` with
`needs: manual credit or refund`. The reconciliation sweep includes
`paid_uncredited` and retries the ledger write. A second defect found while fixing
this — reconciliation could *downgrade* an uncredited order to `failed` on an
inconclusive lookup, losing the payment again — is also fixed: captured money is
treated as a fact.

**Regression:** `test_money_captured_but_uncreditable_stays_retryable`,
`test_uncredited_payment_is_visible_to_a_human`.

### H3 — Double-credit race on a repeated gateway payment
**Location:** `app/models.py` (`Payment`), `app/domain/ledger.py`
(`record_payment`).

**What was wrong:** `record_payment` did a check-then-insert on
`(gateway_provider, gateway_payment_id)` with no database constraint behind it.
The unique index on webhook events is `(provider, event_key)`, so two deliveries
of the *same* payment under different event ids were both stored, could both pass
the existence check, and could both insert a payment. SQLite's single-writer
behaviour hid this in development; PostgreSQL at READ COMMITTED would not.

**Fix:** a unique index on `(gateway_provider, gateway_payment_id)` (migration
`0002`, partial so manual entries with no gateway id do not collide). The lookup
remains as the fast idempotent path, and the database is now the authority.

**Regression:** `test_gateway_payment_id_is_unique_in_the_database`,
`test_two_events_for_one_payment_credit_once`.

---

## Medium

### M1 — Consent gate bypassed for support acknowledgements
**Location:** `app/services/notifications.py` (`send`, `send_support_ack`),
caller `app/web/routes/pay.py` (`portal_support`).

**What was wrong:** the consent check was `if channel in {whatsapp, sms} and
customer is not None`. `send_support_ack` passed `customer=None` and chose its
destination from an arbitrary `contact` value submitted in the form, then sent
with `opt_in=True`.

**Exploit:** with a real WhatsApp/SMS provider configured, anyone holding a valid
portal link could post any phone number as `contact` and have the merchant's
sender message a third party with no consent record — a consent and DLT/TRAI
problem created by a stranger.

**Fix:** the acknowledgement destination now comes only from the customer record
(`_contact_address`), and the real `customer` is passed so the consent gate
applies to that send too. A missing address means no send and a recorded reason.

**Regression:** `test_support_ack_never_targets_a_form_supplied_number`,
`test_support_ack_uses_the_customer_record`.

### M2 — The sandbox gateway remained usable in production
**Location:** `app/main.py` (`_assert_production_ready`), sandbox routes in
`app/web/routes/pay.py` and `app/web/routes/billing.py`.

**What was wrong:** the production start-up check only demanded credentials when
the provider was `razorpay` or `cashfree`. `mock` booted production happily, and
the sandbox routes gated only on the adapter type — no `is_prod` check, even
though the mock *webhook* route already had one.

**Impact:** a deployment left on `mock` would let any portal-link holder mark an
invoice paid with no money. Worse than the "dev-only" limitation claimed in the
docs, because nothing in the code enforced it.

**Fix:** production now **refuses to boot** with `PAYMENT_PROVIDER=mock` or
`MESSAGING_PROVIDER=console`, with an explanatory message. Every sandbox route
additionally returns 404 when `is_prod`.

**Regression:** `test_production_refuses_the_mock_gateway`,
`test_production_accepts_a_real_gateway`,
`test_sandbox_routes_are_unreachable_when_prod`.

### M3 — Billing sandbox completion accepted another organisation's order
**Location:** `app/web/routes/billing.py`, `sandbox_billing_complete()`.

**What was wrong:** the GET screen verified `GatewayOrder.org_id == org.id`; the
POST that actually completes the payment did not. `process_webhook` resolves an
order by `(provider, provider_order_id)` with no org check, so org A could settle
org B's subscription order.

**Fix:** the POST loads the order scoped to the caller's organisation and does
nothing when it is not theirs, matching its GET sibling.

**Regression:** `test_billing_sandbox_cannot_settle_another_orgs_order`.

---

## Low

1. **Rejected webhooks returned 401, causing endless gateway retries.**
   `app/web/routes/webhooks.py` — the docstring promised 2xx for received events
   to suppress retries, but an invalid signature returned 401, so the gateway
   retries forever with no new information. **Fixed:** rejected callbacks now
   return 2xx with `{"status": "rejected"}`; the refusal is recorded in
   `payment_events` and the audit trail, and a rate limit per IP caps the volume.
2. **`with_for_update()` is a no-op on SQLite**, so concurrent invoice creation
   could collide on the per-FY counter and surface as a 500 rather than a retry.
   **Fixed:** the allocation retries once on an integrity error and returns a
   clear message instead of a 500. Production runs PostgreSQL, where the row lock
   is real.
3. **`refund_order()` marked `refund_requested` without reversing the ledger**, so
   refunds were invisible to money totals and sat in no queue.
   **Partially fixed / accepted:** refunds are deliberately not automated (a
   refund is money leaving the merchant's account and must be deliberate), but a
   refunded order now appears in the ops view with status `refund_requested`, and
   the gap is recorded in `docs/HUMAN_TODO.md` as a manual process until the live
   gateway path exists to test against.
4. **`payment_callback()` selected the latest org-level invoice order** rather
   than the invoice's own, so with multiple orders it could no-op.
   **Fixed:** the lookup now matches the invoice id in the order's notes before
   sweeping.

---

## Verified clean (what was checked and found sound)

* **The customer portal cannot be reached without a valid link.** Tokens are an
  HMAC of the customer's stored key and the invoice id under the app secret, 32
  hex characters, compared with `hmac.compare_digest`; a wrong or short token is a
  plain 404. One invoice's link cannot be edited into another's.
* **Payment verification does not trust the browser.** Settlement requires a valid
  signature *and*, for real gateways, a server-to-server order lookup. A callback
  claiming a different amount than the order is quarantined, not applied.
* **Webhook signature verification** is HMAC over the raw body (Razorpay) or the
  documented `timestamp + "." + body` / SDK form (Cashfree), both keyed; an invalid
  signature is recorded and refused.
* **CSRF** covers every unsafe method via `verify_csrf`, and the token is rotated
  on login, signup and OTP login, so a pre-authentication token cannot be replayed.
* **Sessions** are signed with `itsdangerous` bound to the credential hash, so a
  password change invalidates every other device; forged values are rejected.
* **OTP handling**: codes are stored HMAC-hashed, rate limited per phone *and* per
  IP, capped at 5 verification attempts, invalidated when superseded, and the
  endpoint gives an identical response whether or not the number exists.
* **Login**: identical error for unknown account and wrong credential, per-IP rate
  limit, lockout after repeated failures.
* **SQL**: every query goes through SQLAlchemy's parameter binding. No f-string or
  string-concatenated SQL exists in the application code.
* **XSS**: Jinja autoescaping is on for `.html` templates; no `|safe` is used on
  user-controlled data. Stored text is additionally sanitised on input
  (`clean_text` strips control characters and tag-like sequences).
* **Secrets**: gateway credentials are encrypted at rest with Fernet, only ever
  read back masked, and never written into the audit detail. The audit logger
  redacts credential-shaped keys and masks phone numbers, e-mails and long digit
  runs. A live check confirms the settings page never echoes a saved key.
* **Error handling** returns generic messages (`{"detail": "Internal server
  error"}`) and logs the trace to the server only.
* **Headers**: CSP, frame-deny, nosniff, referrer policy, permissions policy and
  HSTS (production only) are set in middleware; the `Server` banner is removed and
  the ASGI server is run with `--no-server-header`.
* **Cross-tenant isolation on the tenant-facing pages** (dashboard, customers,
  invoices, print, export, write-off): every lookup is filtered by `org_id` or
  returns 404, checked route by route and covered by tests.

## Cannot verify from here

* **Live gateway behaviour.** No live keys exist, so Razorpay/Cashfree production
  webhook behaviour, refund APIs and dispute APIs are unexercised. The sandbox
  contract is implemented from their documentation only.
* **Concurrency on PostgreSQL.** The double-credit fix depends on a unique index
  that is created by migration `0002`; the race itself was reasoned about rather
  than reproduced, because the test suite runs on SQLite. A PostgreSQL run is in
  the CI configuration (`deploy/ci.yml`) but has not been executed here.
* **The Cashfree signature discrepancy.** The official SDK hashes
  `timestamp + body` while the documentation specifies `timestamp + "." + body`.
  The adapter accepts either keyed form and records which matched, but which one
  the live service actually sends must be confirmed against sandbox traffic.
