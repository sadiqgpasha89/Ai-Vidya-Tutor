"""SQLite access: one short-lived connection per call, WAL mode, ordered migrations, and online backups."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import config
from .migrations import MIGRATIONS

_lock = threading.RLock()
_ready: set[str] = set()


def path() -> Path:
    return config.DATA_DIR / "teacher.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def migrate() -> int:
    """Apply any migrations not yet recorded. Returns the schema version."""
    with _lock:
        conn = _connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at REAL)")
            done = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
            for version, script in MIGRATIONS:
                if version in done:
                    continue
                conn.executescript("BEGIN;\n" + script + "\nCOMMIT;")
                conn.execute("INSERT INTO schema_version VALUES (?, ?)", (version, time.time()))
                conn.commit()
            return max(v for v, _ in MIGRATIONS)
        finally:
            conn.close()


@contextmanager
def connect():
    key = str(path())
    with _lock:
        if key not in _ready:
            migrate()
            _ready.add(key)
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def one(sql: str, args: tuple = ()) -> dict | None:
    with connect() as db:
        row = db.execute(sql, args).fetchone()
    return dict(row) if row else None


def all(sql: str, args: tuple = ()) -> list[dict]:  # noqa: A001 - mirrors sqlite naming
    with connect() as db:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def run(sql: str, args: tuple = ()) -> int:
    """Execute a write; returns lastrowid."""
    with connect() as db:
        return db.execute(sql, args).lastrowid or 0


def scalar(sql: str, args: tuple = (), default=None):
    with connect() as db:
        row = db.execute(sql, args).fetchone()
    return row[0] if row and row[0] is not None else default


def backup(dest_dir: Path | None = None, keep: int | None = None) -> Path:
    """Consistent online copy of the database (safe while the app is running); prunes old backups."""
    dest_dir = dest_dir or config.DATA_DIR / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / time.strftime("teacher-%Y%m%d-%H%M%S.db")
    with connect() as db:
        target = sqlite3.connect(out)
        try:
            db.backup(target)
        finally:
            target.close()
    for old in sorted(dest_dir.glob("teacher-*.db"))[: -(keep or config.BACKUP_KEEP)]:
        old.unlink(missing_ok=True)
    return out
