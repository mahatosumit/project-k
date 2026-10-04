"""Database engine, session handling, and a tiny forward-only migration runner.

Migrations live in ``app/migrations/*.sql`` and are applied in filename order,
tracked in ``schema_migrations``. Both SQLite (local/test) and PostgreSQL
(production) are supported; the SQL keeps to the common subset.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("vasool.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed on success.

    Committing here matters for security, not just convenience: rate-limit
    counters and failed-login counts are written on *rejected* requests (the 429
    and the wrong-credential paths). If those writes were rolled back at the end
    of the request, throttling would silently never work.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_migration_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL
                )
                """
            )
        )


def applied_migrations(engine: Engine | None = None) -> list[str]:
    engine = engine or get_engine()
    _ensure_migration_table(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT filename FROM schema_migrations ORDER BY filename")).fetchall()
    return [row[0] for row in rows]


_STATEMENT_SPLIT = re.compile(r";\s*\n")


def _split_statements(sql: str) -> list[str]:
    """Split a migration file into statements.

    Comment lines are dropped first so a ``;`` inside a comment cannot break the
    split. Statements are executed one at a time which keeps error reporting
    precise and works identically on SQLite and PostgreSQL.
    """
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    return [s.strip() for s in _STATEMENT_SPLIT.split(body) if s.strip()]


def run_migrations(engine: Engine | None = None, verbose: bool = False) -> list[str]:
    """Apply pending migrations. Returns the list of files applied this run."""
    engine = engine or get_engine()
    _ensure_migration_table(engine)
    done = set(applied_migrations(engine))
    newly: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        with engine.begin() as conn:
            for statement in _split_statements(path.read_text(encoding="utf-8")):
                conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (filename, applied_at) VALUES (:f, CURRENT_TIMESTAMP)"),
                {"f": path.name},
            )
        newly.append(path.name)
        if verbose:
            logger.info("migration applied", extra={"path": path.name})
    return newly


def reset_engine_for_tests() -> None:
    """Drop cached engine/session factory (used by the test suite)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
