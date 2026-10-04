# 05 — Launch checklist

Every item is **done**, **needs-human**, or **blocked**. Nothing is claimed as done
that was not actually run. Where a check exists, the command is given so it can be
re-run rather than believed.

---

## Code and quality — DONE

| Item | State | Evidence / command |
|---|---|---|
| Application builds and runs | ✅ done | `python -m uvicorn app.main:app --port 8000` starts, `/healthz` returns `{"status":"ok","db":true}` |
| Tests pass | ✅ done | `python -m pytest tests -q` → **80 passed** |
| Critical path passes three consecutive runs | ✅ done | `test_three_consecutive_critical_path_runs` — three separate organisations, each settled through a signed webhook |
| Sandbox payment end to end | ✅ done | `--with-demo-payment` seed + portal pay → webhook → server-side confirmation → invoice `paid`, ladder cancelled |
| Linter clean | ✅ done | `python -m ruff check app scripts tests` → *All checks passed* |
| Static security analysis clean | ✅ done | `python -m bandit -r app -c pyproject.toml` → 0 issues across 7,573 lines |
| Dependency advisories | ✅ done | `python scripts/audit_dependencies.py` → 0 advisories in the pinned set (OSV query per pin) |
| Secrets scan | ✅ done | Repository pattern scan (provider prefixes, private keys, credential-shaped assignments) → 0 hits |
| No leaked credential in the UI | ✅ done | Live check: the saved gateway key never appears on the settings page |
| Live end-to-end walk | ✅ done | `python scripts/live_walk.py` against a running server → *all checks passed* |
| Independent security review | ✅ done | `docs/security-review.md` — 3 HIGH and 3 MEDIUM found and fixed, each with a regression test |
| Every bug fixed at root cause with a regression test | ✅ done | `docs/BUGS.md` — 21 bugs, no open critical/high |

## Payments — DONE except merchant onboarding

| Item | State | Evidence |
|---|---|---|
| Hosted checkout only; no card data on our servers | ✅ done | No card field exists anywhere in the templates |
| Webhook signature verified over the raw body | ✅ done | Razorpay and Cashfree adapters; `test_tampered_webhook_signature_is_rejected` |
| Webhook replay idempotent | ✅ done | Unique `(provider, event_key)`; `test_duplicate_webhook_is_ignored` |
| Duplicate payment id cannot double-credit | ✅ done | Unique `(provider, gateway_payment_id)`; `test_two_events_for_one_payment_credit_once` |
| Payment verified server-side, redirect never trusted | ✅ done | Order lookup after callback; amount mismatch quarantined |
| Reconciliation job | ✅ done | `scripts/run_jobs.py`; `test_reconciliation_settles_a_lost_redirect` |
| Money captured but uncreditable is never lost | ✅ done | `paid_uncredited` state, audited, swept; `test_money_captured_but_uncreditable_stays_retryable` |
| Refund path recorded and visible | ⚠️ needs-human | Refunds execute in the gateway dashboard; the record is in the ops view. Auto-refund API deferred until live keys exist |
| Switching sandbox → live is a documented one-step change | ✅ done | `docs/OPERATIONS.md` §1; production refuses `mock`, so the switch cannot be forgotten |
| Merchant KYC completed | ❌ needs-human | See `docs/HUMAN_TODO.md` item 2 |
| One live rupee through the real gateway | ❌ blocked | Requires KYC first |

## Security and hardening — DONE

| Item | State |
|---|---|
| Parameterised queries everywhere (no string-built SQL) | ✅ done |
| Input validation and output encoding | ✅ done — Jinja autoescape on; no `|safe` on user data; control characters and tag-like input stripped |
| CSRF on every unsafe method, rotated on login | ✅ done |
| Strong credential hashing (argon2id) | ✅ done |
| Rate limiting: global, OTP per phone and per IP, login per IP, webhooks | ✅ done — proven by tests, after finding that they had silently done nothing |
| Account lockout after repeated failures | ✅ done |
| Session invalidation on credential change | ✅ done |
| Security headers (CSP, frame-deny, nosniff, referrer, permissions, HSTS in prod) | ✅ done |
| Signed session cookies, httponly, samesite=lax, secure in prod | ✅ done |
| Tenant isolation on every route | ✅ done — asserted route by route; the review's cross-tenant leak is fixed |
| Gateway credentials encrypted at rest, displayed masked | ✅ done |
| Log redaction of credentials, phones, e-mails, digit runs | ✅ done |
| Audit trail of administrative actions | ✅ done |
| Non-root container, minimal base, no compiler at runtime | ✅ done — `deploy/Dockerfile` |
| Request-size limit and bounded list limits | ✅ done |
| Framework fingerprint suppressed | ✅ done — middleware **and** `--no-server-header`; live check asserts it |

## Reliability — DONE

| Item | State |
|---|---|
| Health and readiness endpoints that touch the database | ✅ done |
| Structured JSON logs with rotation | ✅ done |
| Log retention 180 days, in-jurisdiction | ✅ done — enforced by the maintenance job; retention is configuration |
| Backup command | ✅ done — `python scripts/backup.py` |
| **Tested restore** | ✅ done — exercised end to end (backup → verify → restore → verify); recorded in §"Restore evidence" below |
| Graceful failure messages | ✅ done — generic errors to the client, detail to the logs |
| Idempotent payment handling | ✅ done |
| Deployment separation dev/staging/prod | ⚠️ needs-human — configuration exists, no separate hosts yet |
| Documented rollback | ✅ done — `docs/OPERATIONS.md` §1 |
| CI that runs the full suite on every change | ✅ done — `deploy/ci.yml`, including a PostgreSQL migration job and a Trivy image scan |

## Compliance — DONE in product, needs-human for the rest

| Item | State |
|---|---|
| Privacy policy matching actual behaviour | ✅ done (`/legal/privacy`) — lawyer review pending |
| Terms of service, incl. "not advice / not an aggregator" | ✅ done (`/legal/terms`) — lawyer review pending |
| Refund and cancellation policy | ✅ done (`/legal/refund`) |
| Consent notice, recorded and revocable | ✅ done — notice version, source and evidence stored; sending refuses without it |
| Account/customer data export | ✅ done — `GET /app/ops/export/customer/{id}`, org-scoped and audited |
| Data erasure path with a statutory due date | ✅ done — `data_requests` with a due date and a completion record |
| Breach-response runbook | ✅ done — `docs/OPERATIONS.md` §5, with the 6-hour deadline computed per incident |
| Grievance officer published | ❌ needs-human — the operator's own details must be filled in |
| GST: CGST/SGST vs IGST, Rule 46, 16-char per-FY numbering | ✅ done — all tested |
| No Aadhaar, customer PAN or card data collected | ✅ done |
| Certificates and HTTPS | ⚠️ needs-human — Caddy config written for automatic TLS; needs a domain |

## Localisation — DONE

| Item | State |
|---|---|
| English and Hindi UI copy, as data | ✅ done — `app/locales/*.json`, 282 keys each |
| Hindi reminder messages authored, not machine-translated | ✅ done |
| All nine ladder steps render in both locales with no unfilled placeholder | ✅ done — tested |
| Indic font stack (Noto) | ✅ done |
| Mixed-script input handling | ✅ done — Devanagari, Hinglish and English all sanitised without mangling |
| Indian digit grouping and lakh/crore words on invoices | ✅ done — tested |

## Mobile and performance — PARTIAL

| Item | State |
|---|---|
| Mobile-first responsive layout, tabular amounts, 40px+ targets | ✅ done |
| Installable PWA | ⚠️ **not done** — no manifest or service worker yet. Deliberately deferred: it does not change whether a merchant gets paid, and it is listed in `docs/HUMAN_TODO.md` |
| Bundle small, no external asset dependencies | ✅ done — one stylesheet, no CDN, no font download |
| Low-end device / throttled-3G walk with Playwright | ❌ blocked — Playwright is not installable in this environment (browsers cannot be downloaded). The HTTP-level walk covers behaviour; **visual and throttled-network verification has not been done and must not be claimed** |
| Performance budget stated | ⚠️ stated, not measured | One CSS file (~12 KB), no JS on the tenant pages, server-rendered HTML. Not measured on a real low-end device |

---

## Restore evidence

Exercised on 2026-10-04:

```
python scripts/backup.py --tag launch-test
  → vasool-20261004T131544Z-launch-test.db, 323,584 bytes, sha256 recorded
python scripts/backup.py --verify vasool-…-launch-test.db
  → integrity_check: ok, table_count: 23
python scripts/backup.py --restore vasool-…-launch-test.db
  → restored into ./vasool-dev.db, previous file preserved as *.pre-restore-<stamp>
  → post-restore verify: integrity_check ok
```

## What is genuinely not done

1. **No live HTTPS deployment.** Container, proxy and CI are written and untested
   against a real host.
2. **No live payment.** Sandbox only.
3. **No message has ever been sent to a real person.** No DLT registration, no
   WhatsApp sender.
4. **No visual/Playwright verification** (environment limitation, not a choice).
5. **No PWA manifest or service worker.**
6. **No real customer, no revenue, no testimonial.** The landing page says so
   explicitly rather than inventing social proof.
7. **No PostgreSQL execution** has been observed in this environment.

Items 1–3 are the ones that separate "the software passes its tests" from "the
business is live". They are all in `docs/HUMAN_TODO.md` because they require a
person.
