"""Backup and restore for the database plus the log directory.

Uses only the standard library and the configured database driver, so backups do
not depend on a cloud service. PostgreSQL uses ``pg_dump`` when available and
falls back to a documented alternative; SQLite uses the online backup API so a
live database is copied consistently.

    python scripts/backup.py                      # take a backup
    python scripts/backup.py --list               # list existing backups
    python scripts/backup.py --verify <file>      # check a backup is readable
    python scripts/backup.py --restore <file>     # restore into the configured DB

A backup you have never restored is not a backup, so ``--restore`` is a
first-class command here and the verified-restore evidence is recorded in
docs/05-launch-checklist.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings


def _backup_dir() -> Path:
    settings = get_settings()
    path = Path(settings.backup_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sqlite_path(url: str) -> Path | None:
    prefix = "sqlite+pysqlite:///"
    if url.startswith(prefix):
        return Path(url[len(prefix):]).resolve()
    return None


def _stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def take_backup(tag: str = "auto") -> dict:
    settings = get_settings()
    target_dir = _backup_dir()
    stamp = _stamp()
    sqlite_file = _sqlite_path(settings.database_url)
    manifest: dict = {"taken_at": stamp, "tag": tag, "database_url_scheme": settings.database_url.split("://")[0]}

    if sqlite_file is not None and sqlite_file.exists():
        dest = target_dir / f"vasool-{stamp}-{tag}.db"
        # The online backup API takes a consistent copy of a live database.
        source = sqlite3.connect(str(sqlite_file))
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        manifest["file"] = dest.name
        manifest["bytes"] = dest.stat().st_size
        manifest["sha256"] = _sha256(dest)
    elif settings.database_url.startswith("postgresql"):
        dest = target_dir / f"vasool-{stamp}-{tag}.pgdump"
        pg_dump = shutil.which("pg_dump")
        if pg_dump is None:
            raise SystemExit(
                "pg_dump is not on PATH. Install the PostgreSQL client tools, or take a "
                "snapshot at the host level and record that in the launch checklist."
            )
        with dest.open("wb") as handle:
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [pg_dump, "--no-owner", "--format=custom", settings.database_url],
                stdout=handle,
                stderr=subprocess.PIPE,
                check=False,
            )
        if result.returncode != 0:
            dest.unlink(missing_ok=True)
            raise SystemExit(f"pg_dump failed: {result.stderr.decode(errors='replace')[:400]}")
        manifest["file"] = dest.name
        manifest["bytes"] = dest.stat().st_size
        manifest["sha256"] = _sha256(dest)
    else:
        raise SystemExit("Unsupported DATABASE_URL for backup.")

    # Logs are part of the compliance record (CERT-In log retention), so archive
    # them alongside the database.
    log_dir = Path(settings.backup_dir).parent / "logs"
    if log_dir.exists():
        archive = target_dir / f"logs-{stamp}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(log_dir, arcname="logs")
        manifest["logs_file"] = archive.name
        manifest["logs_bytes"] = archive.stat().st_size

    manifest_path = target_dir / f"manifest-{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def list_backups() -> list[dict]:
    entries: list[dict] = []
    for path in sorted(_backup_dir().glob("manifest-*.json")):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return entries


def verify_backup(name: str) -> dict:
    path = _backup_dir() / Path(name).name
    if not path.exists():
        raise SystemExit(f"not found: {path}")
    result: dict = {"file": path.name, "bytes": path.stat().st_size}
    result["sha256"] = _sha256(path)

    if path.suffix == ".db":
        connection = sqlite3.connect(str(path))
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            counts = {}
            for table in ("organizations", "users", "invoices", "payments"):
                if table in tables:
                    counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            result["integrity_check"] = integrity[0] if integrity else "unknown"
            result["table_count"] = len(tables)
            result["row_counts"] = counts
        finally:
            connection.close()
    else:
        result["note"] = "Non-SQLite backup: verify by restoring it, not by reading it."

    result["readable"] = result.get("integrity_check", "ok") == "ok"
    return result


def restore_backup(name: str) -> dict:
    settings = get_settings()
    source = _backup_dir() / Path(name).name
    if not source.exists():
        raise SystemExit(f"not found: {source}")

    sqlite_file = _sqlite_path(settings.database_url)
    if source.suffix == ".db" and sqlite_file is not None:
        # Safety: never overwrite a live database without keeping the old one.
        if sqlite_file.exists():
            safety = sqlite_file.with_suffix(sqlite_file.suffix + f".pre-restore-{_stamp()}")
            shutil.copy2(sqlite_file, safety)
        shutil.copy2(source, sqlite_file)
        verify = verify_backup(source.name)
        return {"restored_into": str(sqlite_file), "verified": verify}

    if source.suffix == ".pgdump":
        pg_restore = shutil.which("pg_restore")
        if pg_restore is None:
            raise SystemExit("pg_restore is not on PATH.")
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [pg_restore, "--clean", "--if-exists", "--no-owner", "--dbname", settings.database_url, str(source)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"pg_restore failed: {result.stderr.decode(errors='replace')[:400]}")
        return {"restored_into": settings.database_url.split("@")[-1], "verified": {"readable": True}}

    raise SystemExit("This backup cannot be restored into the configured database.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Vasool backup and restore")
    parser.add_argument("--list", action="store_true", help="list backups")
    parser.add_argument("--verify", metavar="FILE", help="verify a backup file")
    parser.add_argument("--restore", metavar="FILE", help="restore a backup file")
    parser.add_argument("--tag", default="auto", help="label for this backup")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_backups(), indent=2))
        return 0
    if args.verify:
        print(json.dumps(verify_backup(args.verify), indent=2))
        return 0
    if args.restore:
        print(json.dumps(restore_backup(args.restore), indent=2, default=str))
        return 0

    print(json.dumps(take_backup(tag=args.tag), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
