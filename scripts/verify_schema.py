"""Verify the migration shape on a fresh database.

Runs the migrations in-process (so the app package is importable), then inspects
the resulting schema with plain SQLite to confirm the hardening changes landed.

    python scripts/verify_schema.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "verify-schema.db"
DB_PATH.unlink(missing_ok=True)

import os  # noqa: E402

os.environ["APP_ENV"] = "dev"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{DB_PATH.as_posix()}"

from app.db import applied_migrations, reset_engine_for_tests, run_migrations  # noqa: E402

reset_engine_for_tests()
applied = run_migrations(verbose=True)
print("migrations applied this run:", applied)
print("migrations tracked total :", len(applied_migrations()))

conn = sqlite3.connect(DB_PATH)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("table count:", len(tables))

indexes = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")]
print("payment-related unique indexes:", sorted(i for i in indexes if "payments" in i or "gateway" in i))

checks = [
    ("payment_events", "org_id"),
    ("breach_events", "org_id"),
    ("customers", "portal_link_key"),
    ("organizations", "gateway_key_secret_enc"),
    ("payments", "gateway_payment_id"),
]
for table, column in checks:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    status = "present" if column in cols else "MISSING"
    print(f"  {table}.{column}: {status}")

fk_count = len(list(conn.execute("PRAGMA foreign_key_list(invoices)")))
print("invoices foreign keys:", fk_count)
conn.close()

# Tidy up: the verification database is not a deliverable. Dispose the engine
# first so the file handle is released (Windows will not delete an open file).
reset_engine_for_tests()
DB_PATH.unlink(missing_ok=True)
for suffix in ("-wal", "-shm"):
    Path(str(DB_PATH) + suffix).unlink(missing_ok=True)

print("\nSCHEMA VERIFICATION COMPLETE")
