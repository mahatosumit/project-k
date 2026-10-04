"""Run one job cycle: due reminders, then a gateway sweep.

Intended to be invoked from cron or a scheduler every few minutes. The app does
not depend on it to function — reminders are stored as scheduled rows, so a
missed tick simply means the next tick sends them. That is deliberate: no lost
work if the scheduler is down for a while.

    python scripts/run_jobs.py            # reminders + reconciliation
    python scripts/run_jobs.py --dry-run  # show what would go out
    python scripts/run_jobs.py --reconcile-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.db import run_migrations, session_scope
from app.services import audit as audit_service
from app.services import payments as payment_service
from app.services import ratelimit
from app.services import reminders as reminder_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Vasool job runner")
    parser.add_argument("--dry-run", action="store_true", help="report without sending or settling")
    parser.add_argument("--limit", type=int, default=200, help="max reminders per run")
    parser.add_argument("--reconcile-only", action="store_true", help="skip the reminder dispatch")
    parser.add_argument("--maintenance", action="store_true", help="also prune expired counters and logs")
    args = parser.parse_args()

    settings = get_settings()
    audit_service.configure_logging(log_dir=str(Path(settings.backup_dir).parent / "logs"))
    run_migrations()

    summary: dict = {"dry_run": args.dry_run}
    with session_scope() as session:
        if not args.reconcile_only:
            report = reminder_service.dispatch_due(session, limit=args.limit, dry_run=args.dry_run)
            summary["reminders"] = {
                "attempted": report.attempted,
                "sent": report.sent,
                "blocked_no_consent": report.blocked_no_consent,
                "failed": report.failed,
                "needs_human": report.skipped_human_only,
                "cancelled_settled": report.cancelled_settled,
            }
            if report.errors:
                summary["reminders"]["errors"] = report.errors[:10]

        if args.dry_run:
            summary["reconciliation"] = "skipped (dry run)"
        else:
            summary["reconciliation"] = payment_service.daily_reconciliation(session, settings=settings)

        if args.maintenance and not args.dry_run:
            summary["maintenance"] = {
                "counters_pruned": ratelimit.prune(session),
                "audit_pruned": audit_service.prune_audit(session),
            }

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
