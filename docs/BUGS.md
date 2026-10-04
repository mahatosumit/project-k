# BUGS — every defect found, with root cause and the test that now covers it

Rules applied throughout: fix the **root cause**, and add a **regression test** for
every bug. Nothing here was closed by suppressing the symptom.

**Current state: 0 open critical/high bugs.** 80 tests pass, `ruff` is clean,
`bandit` reports no issues. The bugs below are the fixed historical record, in the
order they were found, because the way they were found is the useful part.

---

## BUG-001 — Templates crashed because a shared lookup was not passed (fixed)
**Symptom:** `GET /app/customers/new` returned 500.
**Root cause:** `customer_form.html` referenced `states`, which the customer route
did not pass into the template context. Any route that forgot a shared lookup
could crash a page.
**Fix:** `states` (and `stage_label`) are injected globally by the templating
helper, so a template cannot depend on a route remembering.
**Covers it:** every page-render assertion in `tests/test_critical_path.py`.

## BUG-002 — CSRF token was not rotated on login (fixed)
**Symptom:** the first authenticated POST after login failed with 403.
**Root cause:** the token issued on the signup/login page stayed in the session, so
a token minted before authentication remained valid after it — and the token found
in the freshly rendered page did not match what the server expected.
**Fix:** a `rotate_csrf` call on every successful authentication (password, signup,
OTP), which also removes a session-fixation style token-replay weakness.
**Covers it:** `test_csrf_is_enforced_on_state_changing_posts`, plus the whole
critical path, which could not pass otherwise.

## BUG-003 — Rate limits and login lockout did nothing (fixed) — **security**
**Symptom:** after 12 OTP requests for the same number, none were refused.
**Root cause:** the request-scoped database session was never committed. Rate-limit
counters and failed-login counts are written on paths that end in a rejection
(429, wrong credential), so their inserts were rolled back at the end of the
request. The protection existed in code and had no effect in practice.
**Fix:** the request session commits on successful exit in `get_db`, so a rejected
request still persists its counter.
**Covers it:** `test_otp_request_is_rate_limited_per_phone`,
`test_login_locks_after_repeated_failures`.

## BUG-004 — OTP limits could be bypassed with an unknown number (fixed) — **abuse**
**Symptom:** discovered while fixing BUG-003 — the limit was only enforced when a
matching account existed, so arbitrary numbers were unthrottled.
**Root cause:** the limit was consumed inside `issue_otp`, which was only reached
for a known phone. The endpoint was an unthrottled oracle for probing numbers and
an unthrottled way to consume someone else's SMS credit.
**Fix:** `enforce_otp_limits` is consumed **before** the account lookup, with
`consume_limits=False` on the issuing call so one request spends one unit.
**Covers it:** `test_otp_request_is_rate_limited_per_phone`,
`test_otp_endpoint_does_not_leak_whether_a_number_exists`.

## BUG-005 — The mock gateway lost its own orders (fixed)
**Symptom:** the sandbox payment flow worked for the first invoice in a process and
then silently stopped settling any further invoice.
**Root cause:** a new `MockAdapter` was constructed per call, so order state created
by a route was invisible to the webhook handler and to reconciliation.
**Fix:** the sandbox adapter is a process singleton, and order ids are randomised
per order (`secrets.token_hex`) so concurrent callers cannot collide on the unique
order id.
**Covers it:** `test_three_consecutive_critical_path_runs`.

## BUG-006 — A real payment was silently swallowed by an id collision (fixed) — **money**
**Symptom:** in the second of three consecutive runs, the invoice stayed unpaid
although the gateway order read `paid`.
**Root cause:** the mock's payment id was derived from the event key's last 8
characters, so two different orders produced the same payment id. The idempotency
lookup in `record_payment` matched the *other* invoice's payment row and returned
it as "already applied", discarding a genuine payment.
**Fix:** payment ids are derived from the order id and event, so they are unique per
order; and — more importantly — if a gateway payment id belongs to a **different**
invoice, the ledger refuses it loudly instead of swallowing the money.
**Covers it:** `test_three_consecutive_critical_path_runs`,
`test_two_events_for_one_payment_credit_once`.

## BUG-007 — Indian multi-level e-mail domains were rejected (fixed)
**Symptom:** seeding failed with `invalid_email` for `demo@vasool.example.co.in`.
**Root cause:** the validator's domain pattern allowed a single dot, which rejects
the common Indian forms (`firm.co.in`, `office.gov.in`).
**Fix:** a domain pattern with one or more labels and a letters-only TLD; tested
against both valid and invalid Indian-shaped addresses.
**Covers it:** `test_signup_is_rejected_for_a_malformed_email` case set in
`tests/test_critical_path.py`.

## BUG-008 — The language switcher did nothing (fixed)
**Symptom:** clicking हिन्दी changed nothing; the link pointed at a URL the page did
not act on.
**Root cause:** the locale was resolved only from the organisation's saved setting,
never from the request, so a public page could not be switched at all.
**Fix:** locale resolution is `?lang=` → cookie → organisation → English, and the
resolved choice is persisted in a cookie so it survives navigation.
**Covers it:** `test_hindi_org_gets_hindi_messages` and the live-walk check that the
Hindi landing page renders.

## BUG-009 — The merchant could not obtain the customer's payment link (fixed)
**Symptom:** the invoice page mentioned a link but rendered nothing usable.
**Root cause:** the portal path was constructed in a route module and never passed
to the invoice template.
**Fix:** link construction moved to `app/services/portal.py` (shared by the portal
routes, the invoice page and the reminder messages) and the path is exposed on the
invoice screen as copyable text.
**Covers it:** the live-walk check "portal link found in the UI".

## BUG-010 — A route function shadowed the service module (fixed)
**Symptom:** `AttributeError: 'function' object has no attribute 'portal_path'`.
**Root cause:** the portal route is named `portal`, which shadowed
`from app.services import portal` at module scope.
**Fix:** the import is aliased (`portal as portal_service`) in every module that
uses it, so a future route named `portal` cannot reintroduce the trap.
**Covers it:** the whole critical path plus `test_portal_requires_a_valid_token`.

## BUG-011 — `Server:` banner leaked the stack (fixed) — **reconnaissance**
**Symptom:** a live check found the header still said `uvicorn` despite middleware
setting `Server: vasool`.
**Root cause:** the ASGI server appends its own header **after** the application
runs, so middleware cannot win on its own.
**Fix:** both — middleware sets `vasool` **and** the server runs with
`--no-server-header` (documented in `docs/OPERATIONS.md` and in the container CMD).
**Covers it:** the live-walk check "no server banner leak".

---

## Fixed after the independent review (`docs/security-review.md`)

| Bug | Severity | What it was | Covers it |
|---|---|---|---|
| BUG-012 | HIGH | The ops dashboard was unscoped: any tenant could read every tenant's webhook payloads, audit trail, data requests and incidents | `test_ops_view_does_not_leak_another_tenants_data`, `test_payment_event_carries_the_owning_org` |
| BUG-013 | HIGH | The order was marked paid **before** the ledger write, so money the ledger refused became invisible with nothing retrying it | `test_money_captured_but_uncreditable_stays_retryable`, `test_uncredited_payment_is_visible_to_a_human` |
| BUG-014 | HIGH | No unique constraint on a gateway payment id: a repeated delivery under a new event id could double-credit | `test_gateway_payment_id_is_unique_in_the_database`, `test_two_events_for_one_payment_credit_once` |
| BUG-015 | MEDIUM | A support acknowledgement could be sent to a number supplied in the request form, bypassing consent entirely | `test_support_ack_never_targets_a_form_supplied_number` |
| BUG-016 | MEDIUM | The sandbox gateway and its routes were usable in production, permitting a fake "paid" state | `test_production_refuses_the_mock_gateway`, `test_sandbox_routes_are_unreachable_when_prod` |
| BUG-017 | MEDIUM | Billing sandbox completion accepted another organisation's order id | `test_billing_sandbox_cannot_settle_another_orgs_order` |
| BUG-018 | MEDIUM | Reconciliation could downgrade a captured-but-uncredited order to `failed`, losing the money a second time (found while fixing BUG-013) | `test_uncredited_payment_is_visible_to_a_human` |
| BUG-019 | LOW | A rejected webhook returned 401, making the gateway retry forever with no new information | `test_unauthenticated_webhook_still_requires_valid_signature` |
| BUG-020 | LOW | The callback page swept the organisation's newest order rather than the invoice's own | the critical path and the live walk |
| BUG-021 | LOW | Invoice-number allocation could surface a concurrent collision as a 500 | `test_invoice_number_is_consecutive_per_financial_year` |

---

## Open, disclosed limitations (not bugs)

1. **No interest figure is shown until `RBI_BANK_RATE_PERCENT` is configured.**
   Deliberate: showing a wrong number in an escalating letter is worse than showing
   none (DECISIONS D-010).
2. **Refunds are a recorded human action, not automated** (review L3). Money
   leaving the merchant's account must be deliberate; the record appears in the ops
   view.
3. **The sandbox adapter confirms an order from our own database** rather than
   re-asking a gateway, because its state is in-process. Every real gateway path
   uses the provider's server-to-server lookup.
4. **No PostgreSQL run has been executed in this environment.** Migrations and the
   unique index are written portably and CI includes a PostgreSQL migration job,
   but the concurrency guarantee has not been observed on PostgreSQL here.
