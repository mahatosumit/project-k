"""Audit logging and the structured application log.

CERT-In direction (No. 20(3)/2022-CERT-In, 28.04.2022) requires logs of all ICT
systems to be kept for a rolling **180 days, within Indian jurisdiction**, and
to be produced to CERT-In on request. We satisfy that by:
* writing security-relevant events to a durable ``audit_log`` table, and
* writing JSON-lines application logs to disk (``LOG_DIR``) that the retention
  policy keeps for ``LOG_RETENTION_DAYS`` (default 180).

The app log deliberately redacts likely secrets and never logs a message body's
recipient in full.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import utcnow as model_utcnow

logger = logging.getLogger("vasool.audit")

_REDACT_KEYS = {
    "password", "passwd", "pwd", "token", "access_token", "refresh_token",
    "authorization", "cookie", "set-cookie", "api_key", "apikey", "key_secret",
    "client_secret", "webhook_secret", "signature", "otp", "code", "secret",
}

# Long digit runs (OTPs, card-like numbers) and e-mail/phone are masked.
_PHONE_RE = re.compile(r"\b(?:\+?91[-\s]?)?[6-9]\d{9}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")


def redact(value: Any) -> Any:
    """Best-effort redaction for anything on its way into a log line."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in _REDACT_KEYS:
                out[k] = "[redacted]"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def scrub_text(text: str) -> str:
    """Mask phone numbers, e-mail addresses and long digit runs in free text."""
    if not text:
        return text
    scrubbed = _EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    scrubbed = _PHONE_RE.sub(lambda m: mask_tail(m.group(0)), scrubbed)
    return _LONG_DIGITS_RE.sub(lambda m: mask_tail(m.group(0)), scrubbed)


def mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    keep = local[:1] if local else ""
    return f"{keep}***@{domain}"


def mask_tail(value: str, keep: int = 2) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) <= keep:
        return "***"
    return "***" + digits[-keep:]


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub_text(str(record.getMessage())),
        }
        for attr in ("event", "org_id", "actor_id", "entity_type", "entity_id", "ip", "path", "status"):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)
        if record.exc_info:
            payload["exc"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(*, log_dir: str | None = None, level: str = "INFO") -> Path | None:
    """Configure JSON logging to stdout and (if writable) a rotating file."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setFormatter(JsonLineFormatter())
    root.addHandler(stream)

    if not log_dir:
        return None
    try:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            path / "app.log", maxBytes=20 * 1024 * 1024, backupCount=30, encoding="utf-8"
        )
        file_handler.setFormatter(JsonLineFormatter())
        root.addHandler(file_handler)
        return path
    except OSError:
        return None


def record(
    session: Session,
    *,
    action: str,
    org_id: str | None = None,
    actor_type: str = "system",
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: Any = None,
) -> AuditLog:
    """Write one immutable audit row. Callers must not pass raw secrets."""
    entry = AuditLog(
        org_id=org_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
        detail=(json.dumps(redact(detail), ensure_ascii=False) if detail is not None else None),
        created_at=model_utcnow(),
    )
    session.add(entry)
    session.flush()
    return entry


def prune_audit(session: Session, *, retention_days: int | None = None) -> int:
    """Delete audit rows past the retention window (default 180 days)."""
    from sqlalchemy import delete as _delete

    days = retention_days or int(os.environ.get("LOG_RETENTION_DAYS", "180") or 180)
    cutoff = model_utcnow() - __import__("datetime").timedelta(days=days)
    result = session.execute(_delete(AuditLog).where(AuditLog.created_at < cutoff))
    session.flush()
    return (result.rowcount or 0)
