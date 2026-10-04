"""Cloudflare Python Worker entrypoint for Vasool / project-k.

Bridges incoming Cloudflare Worker HTTP events to the FastAPI ASGI application
and handles Cloudflare Cron Triggers for the reminder ladder and payment reconciliation.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path so 'app' package is found in all Pyodide/Worker environments
ROOT_DIR = str(Path(__file__).resolve().parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from workers import WorkerEntrypoint, asgi
except ImportError:
    # Fallback / mock base class for local testing and non-worker environments
    class WorkerEntrypoint:  # type: ignore[no-redef]
        def __init__(self, env: Any = None, ctx: Any = None):
            self.env = env
            self.ctx = ctx

    asgi = None  # type: ignore[assignment]

from app.config import get_settings
from app.db import session_scope
from app.main import app
from app.services import payments as payment_service
from app.services import ratelimit
from app.services import reminders as reminder_service

logger = logging.getLogger("vasool.cloudflare")


def sync_cloudflare_env(env: Any) -> None:
    """Propagate Cloudflare bindings and secrets into os.environ."""
    if env is None:
        return

    # Check for Hyperdrive binding or standard environment variables/secrets
    if hasattr(env, "__dict__"):
        for k, v in vars(env).items():
            if not k.startswith("_") and isinstance(v, str):
                os.environ.setdefault(k, v)

    # Some Worker runtimes provide env as a mapping or object with attributes
    for attr in [
        "APP_ENV",
        "APP_NAME",
        "BASE_URL",
        "DATABASE_URL",
        "SECRET_KEY",
        "FIELD_ENCRYPTION_KEY",
        "PAYMENT_PROVIDER",
        "PAYMENT_MODE",
        "MESSAGING_PROVIDER",
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "RAZORPAY_WEBHOOK_SECRET",
        "CASHFREE_APP_ID",
        "CASHFREE_SECRET_KEY",
        "CASHFREE_WEBHOOK_SECRET",
        "WHATSAPP_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "SMS_API_KEY",
        "SMS_API_URL",
        "SMS_SENDER_ID",
        "SMS_DLT_ENTITY_ID",
        "SMS_DLT_TEMPLATE_ID",
    ]:
        val = getattr(env, attr, None)
        if val is not None and isinstance(val, str):
            os.environ.setdefault(attr, val)

    # Hyperdrive connection string mapping
    hyperdrive = getattr(env, "HYPERDRIVE", None) or getattr(env, "DB", None)
    if hyperdrive is not None and hasattr(hyperdrive, "connection_string"):
        os.environ["DATABASE_URL"] = hyperdrive.connection_string


class Default(WorkerEntrypoint):
    """Primary Cloudflare Python Worker Entrypoint."""

    async def fetch(self, request: Any) -> Any:
        """Handle incoming HTTP requests and route through FastAPI via ASGI."""
        sync_cloudflare_env(self.env)
        if asgi is not None:
            return await asgi.fetch(app, request, self.env)
        raise RuntimeError("Cloudflare ASGI connector ('workers.asgi') is not available in this runtime.")

    async def scheduled(self, controller: Any, env: Any, ctx: Any) -> None:
        """Handle scheduled Cron Triggers for due reminders and daily reconciliation."""
        sync_cloudflare_env(env)
        cron_pattern = getattr(controller, "cron", "cron_trigger")
        logger.info("Executing scheduled cron job: %s", cron_pattern)

        settings = get_settings()

        try:
            with session_scope() as session:
                # 1. Dispatch due reminders
                report = reminder_service.dispatch_due(session, limit=200, dry_run=False)
                logger.info(
                    "Reminder dispatch: sent=%d, failed=%d, blocked=%d, human_needed=%d",
                    report.sent,
                    report.failed,
                    report.blocked_no_consent,
                    report.skipped_human_only,
                )

                # 2. Daily reconciliation sweep
                reconcile_report = payment_service.daily_reconciliation(session, settings=settings)
                logger.info("Reconciliation sweep complete: %s", reconcile_report)

                # 3. Rate-limit and expired maintenance pruning
                ratelimit_pruned = ratelimit.prune(session)
                logger.info("Maintenance complete: pruned %d rate limit counters", ratelimit_pruned)

        except Exception as exc:
            logger.exception("Scheduled job cycle failed: %s", exc)


# Export the FastAPI app for direct ASGI server runners
__all__ = ["Default", "app", "sync_cloudflare_env"]
