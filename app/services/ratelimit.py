"""Database-backed fixed-window rate limiting and OTP abuse protection.

Deliberately dependency-free (no Redis required to run the product), while
keeping the interface small enough that a Valkey/Redis adapter can replace the
storage later without touching callers.

Protects: OTP endpoints (SMS-pumping fraud), login attempts (credential
stuffing), webhook endpoints, and a coarse global per-IP ceiling.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import RateCounter
from app.models import utcnow as model_utcnow


@dataclass(frozen=True)
class RateVerdict:
    allowed: bool
    remaining: int
    limit: int
    retry_after_seconds: int


def _window_start(now: dt.datetime, window_seconds: int) -> dt.datetime:
    epoch = int(now.timestamp())
    bucket = epoch - (epoch % window_seconds)
    return dt.datetime.fromtimestamp(bucket, tz=dt.UTC).replace(tzinfo=None)


def _fixed(value: str, length: int = 100) -> str:
    """Hash long/dirty keys so the unique index stays small and safe."""
    if len(value) <= length:
        return value
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def hit(
    session: Session,
    *,
    bucket: str,
    key: str,
    limit: int,
    window_seconds: int = 3600,
    now: dt.datetime | None = None,
) -> RateVerdict:
    """Consume one unit from a fixed window. Atomic under concurrent requests."""
    now = now or model_utcnow()
    start = _window_start(now, window_seconds)
    safe_key = _fixed(key or "unknown")

    row = session.scalar(
        select(RateCounter).where(
            RateCounter.bucket == bucket,
            RateCounter.key == safe_key,
            RateCounter.window_start == start,
        )
    )
    if row is None:
        row = RateCounter(bucket=bucket, key=safe_key, window_start=start, count=0)
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            # Another request inserted first; fall back to the existing row.
            session.rollback()
            row = session.scalar(
                select(RateCounter).where(
                    RateCounter.bucket == bucket,
                    RateCounter.key == safe_key,
                    RateCounter.window_start == start,
                )
            )
            if row is None:
                return RateVerdict(False, 0, limit, window_seconds)

    if row.count >= limit:
        elapsed = int((now - start).total_seconds())
        retry_after = max(1, window_seconds - elapsed)
        return RateVerdict(False, 0, limit, retry_after)

    row.count += 1
    session.flush()
    return RateVerdict(True, max(0, limit - row.count), limit, 0)


def peek(
    session: Session,
    *,
    bucket: str,
    key: str,
    window_seconds: int = 3600,
    now: dt.datetime | None = None,
) -> int:
    now = now or model_utcnow()
    start = _window_start(now, window_seconds)
    row = session.scalar(
        select(RateCounter).where(
            RateCounter.bucket == bucket,
            RateCounter.key == _fixed(key or "unknown"),
            RateCounter.window_start == start,
        )
    )
    return int(row.count) if row else 0


def prune(session: Session, *, older_than_hours: int = 48, now: dt.datetime | None = None) -> int:
    """Housekeeping: drop expired windows. Called by the maintenance job."""
    now = now or model_utcnow()
    cutoff = now - dt.timedelta(hours=older_than_hours)
    result = session.execute(delete(RateCounter).where(RateCounter.window_start < cutoff))
    session.flush()
    return (result.rowcount or 0)
