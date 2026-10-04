# STATE — where this build actually is

**Last updated:** 2026-10-04
**Phase:** 1–8 complete. Functionality finished, hardened, audited. **Launch is
blocked on human-only actions.**
**Honest headline:** the software works and is tested end to end with a sandbox
gateway. It has **no real customers**, has **never processed a real rupee**, and
several regulatory questions remain UNVERIFIED. Do not describe it as launched.

---

## Final verification (re-run these to confirm, do not take them on trust)

| Check | Command | Result |
|---|---|---|
| Test suite | `python -m pytest tests` | **80 passed** |
| Linter | `python -m ruff check app scripts tests` | **All checks passed** |
| Static security analysis | `python -m bandit -r app -c pyproject.toml` | **No issues identified** (7,716 lines) |
| Dependency advisories | `python scripts/audit_dependencies.py` | **No known advisories** in the pinned set |
| Migrations on a fresh database | `python scripts/verify_schema.py` | 2 migrations, 23 tables, unique index `ux_payments_gateway_payment` present |
| Critical path, three consecutive runs | `pytest tests -k three_consecutive` | **passes** — three organisations, each settled through a signed webhook |
| Live server walk | `python scripts/live_walk.py` | **all checks passed** against a running server |
| Backup and **verified restore** | `python scripts/backup.py` → `--verify` → `--restore` | **exercised**, integrity ok |

`scripts/audit_dependencies.py` exists because `pip-audit` cannot run in this
environment (the bundled Python lacks the `venv` module). It performs the same
check by querying the OSV database per pinned version.

---

## What is done

| Area | State |
|---|---|
| Problem research — 27 problems, competitors, bottom-up sizing | Done, sourced in `docs/01-problems.md` |
| Validation and kill criteria | Done in `docs/02-validation.md`; kill date written before the pilot |
| Product definition — PRD, threat model, compliance map | `docs/03-prd.md`, `docs/03-threat-model.md`, `docs/03-compliance-map.md` |
| Regulatory research — GST, gateways, DPDP/CERT-In, messaging, hosting | `research/03`, `research/04`, `research/05`; gaps explicitly marked UNVERIFIED |
| Application | Auth (password + OTP), customers, invoices, the 9-step ladder, customer portal, own-gateway payments, billing, admin, ops/compliance views |
| Bilingual | English and Hindi as data files (282 keys each), authored Hindi message copy |
| Tests | 80, including 12 written specifically for the security review's findings |
| Independent security review | `docs/security-review.md` — 3 HIGH + 3 MEDIUM found, all fixed with regression tests |
| Bug record | `docs/BUGS.md` — 21 bugs, every one fixed at root cause with a test |
| Operations | `docs/OPERATIONS.md` — deploy, rollback, monitoring, backup/restore drill, incident runbook |
| Deployment assets | `deploy/Dockerfile` (non-root, multi-stage), `deploy/docker-compose.yml`, `deploy/Caddyfile` (automatic HTTPS), `deploy/ci.yml` (full suite + PostgreSQL migration + Trivy + SBOM) |
| Launch assets | Landing page, pricing page, four legal pages, go-to-market plan, 20 outreach drafts, 10 SEO keywords |
| Dependency audit | `docs/DEPENDENCIES.md` — every package, licence, reason, alternative considered |

## What is deliberately not done

* **No live payment keys.** Sandbox only. Merchant KYC is a human action.
* **No message has ever been sent to a real person.** No DLT registration and no
  WhatsApp sender exist, so the SMS adapter refuses to send and WhatsApp has no
  approved templates.
* **No live HTTPS deployment.** Container, proxy and CI are written and untested
  against a real host.
* **No PostgreSQL execution observed.** Migrations are portable and CI includes a
  PostgreSQL job, but the concurrency guarantee has not been run there.
* **No visual or throttled-network verification.** Playwright could not be installed
  here (browsers cannot be downloaded), so low-end-device rendering is unproven.
  The HTTP-level walk covers behaviour, not appearance.
* **No PWA manifest or service worker.** Deferred: it does not change whether a
  merchant gets paid.
* **No customers, revenue, testimonials or reviews.** The landing page says so
  rather than inventing social proof.

## Open bugs

**Zero open critical or high severity bugs.** Two disclosed limitations, both
intentional and surfaced in the UI rather than hidden:

1. **MSMED interest shows no figure** until `RBI_BANK_RATE_PERCENT` is configured
   (D-010) — showing a wrong number in an escalating letter is worse than none.
2. **Refunds are a recorded human action**, not automated, because money leaving a
   merchant's account must be deliberate.

## Next 3 actions

1. **Talk to 20 Indian service-business owners.** One question: *what is the oldest
   invoice you are still waiting on, and what have you done about it?* Then ask for
   ₹499 up front. Nothing else matters until that answer is in — the kill criteria
   are already written in `docs/02-validation.md`.
2. **Start entity registration and gateway merchant KYC in parallel.** Longest
   external lead time, and it blocks live money (`docs/HUMAN_TODO.md` items 1–2).
3. **Deploy to a real HTTPS host** on an India-region provider, re-run
   `scripts/live_walk.py` against it, and put the app on a low-end Android phone for
   an hour of real use.

## Key decisions

Nineteen decisions with reasons and sources are in `docs/DECISIONS.md`. The
load-bearing ones: the product choice (D-001), service firms not micro-retail
(D-002), prepaid instead of auto-debit (D-003), the merchant's own gateway so we
are not a payment aggregator (D-004), server-side payment verification (D-005),
consent checked twice and a refusal logged (D-011), and a human always sends the
final notice (D-012).

## How to resume after a context reset

1. Read this file, then `docs/BUGS.md` and `docs/HUMAN_TODO.md`.
2. `python -m pip install -r requirements-dev.txt`
3. `python -m pytest tests` — expect **80 passed**. If not, fix before anything
   else; the critical-path tests are the definition of "the product works".
4. `python scripts/seed_demo.py --with-demo-payment`
5. `python -m uvicorn app.main:app --port 8000 --no-server-header`, then
   `python scripts/live_walk.py` — expect all checks passing.
6. For any real deployment work, read `docs/OPERATIONS.md` first.

**If you are about to describe this product to anyone:** it is built and tested,
it is not launched, and it has never handled a real payment. `docs/FINAL_REPORT.md`
is the honest summary to share.
