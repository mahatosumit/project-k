# Architecture and stack justification

## The stack, in one paragraph

**FastAPI + Jinja2 + SQLAlchemy, on SQLite in development and PostgreSQL in
production, behind Caddy, in one container.** FastAPI was chosen because a
collection product is mostly *scheduled effects on data* — one reminder ladder, one
payment ledger — so the valuable things to get right are the domain logic and the
testability, not the front end. FastAPI's dependency injection puts authentication,
CSRF and rate limiting in one place that a route cannot forget, and its test client
made it possible to write a full critical-path test (signup → invoice → ladder →
payment → settlement) that runs in under a second. Templates are server-rendered
with autoescaping on, which removes an entire class of XSS bug and means the
product works on a low-end Android phone over 3G without a JavaScript bundle.
SQLAlchemy gives one portable query layer for both databases and parameter binding
everywhere, so SQL injection is a solved property rather than a code-review habit.

## Why not the alternatives

| Alternative | Rejected because |
|---|---|
| Django | Its admin and ORM conventions are excellent, but the built-in admin is not what a merchant needs, and the framework surface is several times what this product uses. The deciding factor: the ladder is the product, and Django does not make the ladder easier to test. |
| Next.js / React SPA | A JavaScript bundle on a ₹6,000 Android phone over patchy 3G is a real cost, and server-rendered HTML already satisfies the PWA requirement's *purpose*. It also moves form handling and CSRF into two places instead of one. |
| Rails | Viable, but the team's stated skills are Python and the payment/messaging adapters benefit from Python's ecosystem. |
| Flask | No built-in validation or dependency injection; the auth/CSRF/rate-limit plumbing would have been hand-wired and easy to forget on a new route. |

## Layering, and the rule each layer exists to enforce

```
app/
  adapters/     swappable edges: payments (Razorpay, Cashfree, mock) + messaging
  domain/       pure logic: money, GST, MSMED interest, ledger, the ladder
  services/     transactions and orchestration: auth, payments, reminders, consent
  web/          routes, dependencies, Jinja templates, CSS
  migrations/   numbered .sql, applied in order
  locales/      UI copy as data
```

* **`domain/` has no database and no HTTP.** That is why the GST split, the Indian
  money formatting and the MSMED arithmetic are unit-tested without a fixture, and
  why the same functions run in a template, a job and a test.
* **`services/` owns transactions and the invariants that span tables.** Applying a
  payment, stopping a ladder, writing an audit row — all in one place, so a route
  cannot half-do it.
* **`adapters/` is where a third party lives.** Adding Cashfree after Razorpay, or
  a second country's gateway later, means writing an adapter, not editing the
  product. `TestClient` plus the mock adapter means the whole payment path is
  exercised in tests with no network and no rupee.
* **`web/` is thin on purpose.** Routes validate input, authorise, call a service,
  and render. The authorisation helper (`owned_customer`, org-scoped lookups) exists
  so that "check it belongs to this org" is a call, not a habit.

## Data model decisions

* **Money is always integer paise.** Never a float. A rounded rupee is a bug
  someone discovers in a reconciliation.
* **Primary keys are text UUIDs.** No dialect-specific autoincrement, so the same
  migration runs on SQLite and PostgreSQL.
* **The payments table is the source of truth; the invoice's `paid_paise` is a
  cache.** The nightly reconciliation re-derives the cache and treats a mismatch as
  a bug indicator rather than silently fixing it.
* **Uniqueness is enforced in the database where it protects money**:
  `(provider, event_key)` on webhook events and `(provider, gateway_payment_id)` on
  payments. A check-then-insert is not a guarantee — that lesson cost a real defect
  (BUG-014).
* **Consent is a table, not a boolean.** Purpose, notice version, source and
  timestamps, so a later change to the notice cannot silently retro-apply.

## Request lifecycle

```
Caddy (TLS, body limit, real client IP)
  → BodyLimitMiddleware        (1 MiB cap)
  → RequestContextMiddleware   (request id, structured access log, safe 500)
  → SecurityHeadersMiddleware  (CSP, frame-deny, HSTS in prod, Server banner)
  → SessionMiddleware          (signed cookie for CSRF)
  → enforce_global_rate_limit  (dependency: per-IP ceiling)
  → route                      (verify_csrf → authorise → service → render)
  → get_db                     (commit on success, including rejected requests —
                                rate-limit counters depend on it: BUG-003)
```

## The payment path, end to end

```
customer opens /pay/{invoice_id}/{link_key}
    link_key = HMAC(customer.portal_link_key, invoice_id) under the app secret
  → taps Pay
  → service creates a gateway order (hosted checkout; no card data here)
  → customer pays on the gateway's own page
  → gateway calls back: verified HMAC over the raw body, stored against a unique
    (provider, event_key)
  → for real gateways, server-side order lookup is the authority (never the redirect)
  → amount checked against the order: a mismatch is quarantined, not applied
  → ledger.record_payment (idempotent; the DB unique index is the backstop)
  → order marked paid ONLY after the ledger accepts the money
  → ladder cancelled, merchant notified, audit written
  → anything that could not be credited becomes paid_uncredited and is swept daily
```

## Testing strategy

* **Domain unit tests** for the arithmetic that is expensive to get wrong: the
  CGST/SGST/IGST split foots to the total for every amount tested, Indian digit
  grouping, lakh/crore words, MSMED interest, stage progression, ladder ordering.
* **A full critical-path test** through the real HTTP stack, settling an invoice
  through a signed webhook and asserting the ladder stopped.
* **Three consecutive critical-path runs** as an exit criterion, because "it worked
  once" is not a payment system.
* **Adversarial tests** as first-class citizens: tampered signatures, duplicate
  webhooks, amount mismatch, cross-tenant access, CSRF, OTP abuse, lockout,
  consent withdrawal, forged sessions, sandbox access in production.
* **A live walk** against a running server (`scripts/live_walk.py`), because a test
  client does not exercise the ASGI server's own headers and behaviour.

## Known architectural limitations

1. **Rate limiting is database-backed**, so it costs a write per request. Correct
   for now; the interface is deliberately small enough to swap to Valkey.
2. **Reminder dispatch is a cron-style job**, not a queue. Reminders are stored rows,
   so a missed tick delays rather than loses them — which is the right trade for a
   single-instance deployment.
3. **The mock gateway is in-process**, so production refuses it outright.
4. **No horizontal session state**, so the app scales by adding stateless replicas;
   only the sandbox adapter would care, and it cannot run in production.
