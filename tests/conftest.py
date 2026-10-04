"""Test configuration.

Every test function runs against a **fresh** database in a temp directory with
deterministic signing material and the console messaging sink. Nothing here can
touch a real gateway, a real message, or the developer's own data.

Environment must be configured before any application import, because settings
are built from the environment at import time.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="vasool-tests-"))

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("SECRET_KEY", "test-run-signing-material-0123456789abcdef")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "test-run-field-material-0123456789abcdef")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")
os.environ.setdefault("PAYMENT_MODE", "sandbox")
os.environ.setdefault("MESSAGING_PROVIDER", "console")
os.environ.setdefault("BACKUP_DIR", str(_TMP))
os.environ.setdefault("GLOBAL_RATE_LIMIT_PER_MINUTE", "10000000")
os.environ.setdefault("OTP_MAX_PER_PHONE_PER_HOUR", "5")
os.environ.setdefault("OTP_MAX_PER_IP_PER_HOUR", "20")
os.environ.setdefault("LOGIN_MAX_PER_IP_PER_HOUR", "1000")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import db as db_module  # noqa: E402
from app.main import app  # noqa: E402

_counter = {"n": 0}


@pytest.fixture(autouse=True)
def fresh_database(monkeypatch):
    """Give every test its own database file and its own engine.

    Sharing one database across tests would make user-uniqueness and counters leak
    between tests, which hides real bugs and invents fake ones.
    """
    _counter["n"] += 1
    path = _TMP / f"test-{_counter['n']:04d}.db"
    url = f"sqlite+pysqlite:///{path.as_posix()}"

    engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(db_module, "_engine", engine, raising=False)
    monkeypatch.setattr(db_module, "_SessionLocal", factory, raising=False)
    db_module.run_migrations(engine)

    # The mock gateway is a process singleton; clear its in-memory orders so each
    # test starts with no gateway state either.
    from app.adapters import payments as payments_module

    monkeypatch.setattr(payments_module, "_MOCK_SINGLETON", None, raising=False)

    yield
    engine.dispose()
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


@pytest.fixture()
def session():
    factory = db_module.get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.fixture()
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def csrf_of(html: str) -> str | None:
    """Pull the CSRF value out of a rendered page."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html or "")
    return match.group(1) if match else None


@pytest.fixture()
def csrf():
    return csrf_of
