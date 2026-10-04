# OPERATIONS — deploy, monitor, back up, recover, and respond to incidents

Audience: whoever is on call. Assume they are tired and unfamiliar with the code.

---

## 1. Deploy

### Local, from a checkout

```bash
python -m pip install -r requirements-dev.txt
export APP_ENV=dev SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export FIELD_ENCRYPTION_KEY="$(python -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
python scripts/seed_demo.py --with-demo-payment
python -m uvicorn app.main:app --reload --port 8000 --no-server-header
```

### Container, with PostgreSQL and TLS

```bash
cd deploy
cp ../.env.example .env      # then set SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD
docker compose up --build -d
docker compose logs -f app
curl -fsS http://localhost:8080/readyz
```

Migrations run automatically at application start-up. They are numbered `.sql`
files applied in order and recorded in `schema_migrations`, so a restart is safe
and re-running never reapplies one.

### Switching from sandbox to live payments

This is a configuration change, not a code change:

1. Complete merchant KYC at the gateway and obtain live keys.
2. Set `PAYMENT_MODE=live`, `PAYMENT_PROVIDER=razorpay` (or `cashfree`), and the
   platform key id/secret plus the webhook signing key.
3. Register the webhook URL at the gateway: `{BASE_URL}/webhooks/{provider}`.
4. Restart. In production the app **refuses to start** with the mock provider or
   the console messaging sink — that refusal is the safety net.
5. Take one live ₹1 payment through the portal end to end, then refund it through
   the gateway dashboard and confirm the refund appears in the ops view.

### Rolling back

* **Application:** deploy the previous image tag. The app is stateless; no
  migration is destructive, so an older build runs against a newer schema.
* **Data:** see §3. A rollback does not require a restore unless a migration was
  wrong, and migrations here only add columns and indexes.
* **Never** roll back by deleting `schema_migrations` rows; apply a new forward
  migration instead.

---

## 2. Monitor

| What | How | Alert when |
|---|---|---|
| Liveness | `GET /healthz` (touches the database) | Non-200 for 2 consecutive checks |
| Readiness | `GET /readyz` — used by the container health check | Non-200 |
| Errors | JSON log lines with `"level": "ERROR"`, plus `unhandled error` | Any occurrence; investigate immediately |
| Payment health | Ops page → recent gateway callbacks; `scripts/run_jobs.py` output | `orders_pending` rising, or any `uncredited_remaining > 0` |
| Money stuck | Ops page audit rows for `payment.uncredited`, `payment.amount_mismatch`, `payment.ledger_conflict` | Immediately — each is a real payment needing a human |
| Messaging | `notification_log` growth; ops 7-day count | A sudden drop to zero means the provider broke |
| Abuse | 429s in the log, `auth.otp_rate_limited`, `auth.login_rate_limited` audit rows | Spike, or one IP dominating |
| Uptime | Any external monitor against `/healthz` | — |

**The single most important alert is `payment.uncredited`.** Everything else is
availability; that one is money.

---

## 3. Backup and restore

```bash
# Take a backup (SQLite uses the online backup API; PostgreSQL uses pg_dump)
python scripts/backup.py --tag nightly

# List what exists
python scripts/backup.py --list

# Prove a backup is real BEFORE you need it
python scripts/backup.py --verify vasool-<stamp>-nightly.db

# Restore (keeps the previous database aside as *.pre-restore-<stamp>)
python scripts/backup.py --restore vasool-<stamp>-nightly.db
```

**Retention:** keep 7 daily, 4 weekly and 12 monthly copies. Backups include the
log directory, because the logs are part of the incident record.

**Restore drill (do this quarterly, and before going live):**
1. Take a fresh backup.
2. Restore it into a scratch environment.
3. `--verify` the restored file and confirm the row counts match production.
4. Start the app against the restored database and log in.
5. Record the date and the outcome in `docs/05-launch-checklist.md`.

**A backup you have never restored is not a backup.** That is why `--restore` is a
first-class command and not a footnote.

---

## 4. Scheduled jobs

```bash
# Every 5 minutes: dispatch due reminders, then sweep pending gateway orders
python scripts/run_jobs.py

# Hourly, additionally: prune expired rate-limit counters and old audit rows
python scripts/run_jobs.py --maintenance

# See what would go out without sending
python scripts/run_jobs.py --dry-run
```

Reminders are **stored rows**, not in-request sends, so a missed tick means the next
tick sends them — nothing is lost. Do not run two scheduler instances against the
same database at the same second; the dispatch is safe either way (unique steps,
single status transition) but it will log duplicate attempts.

Example cron:
```cron
*/5 * * * * cd /app && /opt/venv/bin/python scripts/run_jobs.py >> /data/logs/jobs.log 2>&1
0 * * * *   cd /app && /opt/venv/bin/python scripts/run_jobs.py --maintenance >> /data/logs/jobs.log 2>&1
15 2 * * *  cd /app && /opt/venv/bin/python scripts/backup.py --tag nightly >> /data/logs/backup.log 2>&1
```

---

## 5. Incident response runbook

**Trigger:** any suspected unauthorised access, data exposure, credential leak,
successful abuse of the OTP or login paths, or an unexplained change in payment
behaviour.

**Clock:** CERT-In Direction No. 20(3)/2022-CERT-In requires reporting within
**6 hours** of noticing, not 6 hours of resolving.

| Step | Time | Action |
|---|---|---|
| 1. Record | T+0 | Ops page → **Record an incident**: severity, what happened, affected count. This starts the deadline clock. Do not wait for a full picture. |
| 2. Contain | T+15m | Rotate `SECRET_KEY` (ends every session), rotate the affected gateway keys at the provider and in each merchant's settings, and block the offending source at the reverse proxy. |
| 3. Preserve | T+30m | Copy the logs and database aside **before** any cleanup. Evidence is lost by fixing first. |
| 4. Assess | T+1h | What data, whose, how many subjects? Was money moved? Was a credential exposed? |
| 5. Report | **before T+6h** | Report to CERT-In. Notify affected merchants. Where DPDP requires it, notify affected individuals. |
| 6. Eradicate | same day | Fix the vulnerability, not just the symptom. Add a regression test. |
| 7. Review | within 7 days | Update this runbook, `docs/security-review.md` and `docs/BUGS.md`. State plainly what was missed. |

**Incident contact:** the operator's own details must be filled in on
`/legal/grievance`, alongside the CERT-In reporting contact. That page is
intentionally a placeholder until a human completes it.

**If money is involved**, the money-handling order is: stop the bleeding (rotate
keys), then establish what actually happened from `payment_events` and the audit
trail, then reconcile invoices before informing anyone of amounts.

---

## 6. Routine maintenance

| Cadence | Task |
|---|---|
| Daily | Check the ops page for `uncredited`, `amount_mismatch`, `ledger_conflict` rows; confirm the nightly backup exists |
| Weekly | Read error logs; check gateway settlement against invoices; review reminder send rate |
| Monthly | Restore a backup into a scratch environment; re-run `python scripts/audit_dependencies.py`; review audit rows for unexpected administrative actions |
| Quarterly | Restore drill recorded in the launch checklist; review access to the host; re-verify GST/DPDP/CERT-In rules against the official sources (they change) |
| On dependency release | Update pins deliberately, re-run the full suite, then deploy |

---

## 7. Known operational limitations

1. **Rate limiting is database-backed**, so it adds a write per request. Correct
   for now; swap to Valkey behind `app/services/ratelimit.py` if write volume grows.
2. **The mock gateway is single-process.** Fine for development and tests; never
   for production, and the app refuses to start that way in production.
3. **`request.client.host` is the rate-limit key.** Behind a proxy this is the
   proxy unless the app runs with `--proxy-headers` and the proxy strips incoming
   `X-Forwarded-For`. The container CMD does both; do not expose the app port
   directly to the internet.
4. **A single application instance is assumed** for the in-process sandbox adapter
   only. Real gateway flows are stateless and scale horizontally.
