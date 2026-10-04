# Vasool — receivables follow-up for Indian service businesses

A small, self-hostable web app that chases unpaid invoices politely and
persistently over WhatsApp and SMS, takes the payment through the merchant's own
gateway, and hands them a documented evidence pack when a customer will not pay.

**Status: pre-launch. Sandbox payments only. No real customers yet.**
Every claim in these docs is either sourced or explicitly marked unverified.

---

## What it does

1. **Record the invoice.** Customer, amount, due date. GST is split into
   CGST+SGST or charged as IGST based on the supplier's and buyer's states, and
   the printed invoice carries the Rule 46 particulars.
2. **See the ladder before it runs.** Nine touches over about four months, from
   a friendly nudge three days before the due date to a formal MSMED-aware
   letter. Every message is shown in English or Hindi and nothing is sent that
   the merchant has not seen.
3. **Let the customer respond.** The portal lets them pay, claim they already
   paid, dispute the amount, or ask for instalments. Any of those stops the
   ladder and alerts the merchant.
4. **Settle the truth, not the redirect.** A payment is applied only after the
   gateway's own server-to-server lookup confirms it. Webhooks are
   signature-verified, replay-proof and idempotent, with a daily reconciliation
   sweep for anything that got lost.

## What it deliberately is not

* **Not a payment aggregator.** Money moves through the merchant's own gateway
  and never through us.
* **Not advice.** No tax, legal or investment guidance. MSMED interest stays
  blank unless the RBI bank rate has been configured, rather than guessing.
* **No hardware, no lending, no betting, no medical, no crypto** — outside the
  scope on purpose (see `docs/DECISIONS.md`).

---

## Quick start (development)

```bash
python -m pip install -r requirements-dev.txt

cp .env.example .env          # then fill in SECRET_KEY and FIELD_ENCRYPTION_KEY
export APP_ENV=dev
export PAYMENT_PROVIDER=mock  # sandbox adapter, no real gateway
export MESSAGING_PROVIDER=console  # logs messages instead of sending them

python scripts/seed_demo.py --with-demo-payment
python -m uvicorn app.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000> and log in with the seeded account:

```
demo@vasool.example.in
demo-account-123
```

`--no-server-header` is recommended (see `docs/OPERATIONS.md`): it stops the ASGI
server from re-adding a `Server:` banner after the app has removed it.

### Tests and QA

```bash
python -m pytest tests -q            # 68 tests: domain maths + critical path + abuse cases
python scripts/run_jobs.py --dry-run # what the reminder ladder would send right now
python scripts/live_walk.py          # walk a RUNNING server over real HTTP
python scripts/backup.py --tag dev   # back up, then verify and restore it
```

---

## Layout

```
app/
  adapters/      payments (Razorpay, Cashfree, mock) and messaging, behind interfaces
  domain/        pure logic: money/Indian formatting, GST, MSMED interest, ledger, ladder
  locales/       UI copy as data — en.json, hi.json
  migrations/    numbered .sql, applied in order and tracked
  services/      auth, audit, notifications, payments, portal links, rate limiting, reminders
  web/           routes + Jinja templates + CSS
scripts/         job runner, seeder, backup/restore, live walk
tests/           pytest suite
docs/            decisions, state, PRD, threat model, compliance, launch checklist, report
research/        sourced evidence: market problems, GST/tax, gateways, DPDP/messaging/hosting
deploy/          Dockerfile, Caddyfile, CI, cron
```

## Configuration

All configuration is environment variables. See `.env.example` for the full
reference. The two that must never be committed are `SECRET_KEY` (session and
CSRF signing) and `FIELD_ENCRYPTION_KEY` (encrypts each merchant's gateway
credentials at rest); the app **refuses to start** in staging/production without
them.

## Going live with real money

Switching from sandbox to live payments is a configuration change, not a code
change: set `PAYMENT_MODE=live` and supply live keys. The steps that a human
must complete first — merchant KYC, GST registration decisions, DLT and WhatsApp
sender approvals, and a CA/lawyer review — are listed with time estimates in
`docs/HUMAN_TODO.md`.

## Licence and provenance

All runtime dependencies are permissively licensed and pinned; the audit is in
`docs/DEPENDENCIES.md`. Payment integrations use the providers' own official
Python SDKs.
