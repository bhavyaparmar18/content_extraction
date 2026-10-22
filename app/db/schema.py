"""Versioned schema migrations for ``app.db``.

``migrations/NNNN_name.sql`` files are applied in order, each in its own
transaction, for every number above the database's ``PRAGMA user_version``,
which is then set to that number. A schema change is a new file
(``0002_add_x.sql``), never an edit to an applied one.

Every store calls ``ensure_schema`` on construction; after the first call per
path it returns immediately.
"""

import re
import sqlite3
import threading
from pathlib import Path

from app.db.connection import connect

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_NAME = re.compile(r"^(\d{4})_[A-Za-z0-9_]+\.sql$")

_lock = threading.Lock()
_ready: set[str] = set()


def migrations() -> list[tuple[int, Path]]:
    found = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = _NAME.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort()
    numbers = [n for n, _ in found]
    if numbers != list(range(1, len(numbers) + 1)):
        raise RuntimeError(f"schema migrations must be numbered 0001, 0002, ... without gaps: {numbers}")
    return found


def latest_version() -> int:
    return len(migrations())


def _statements(sql: str) -> list[str]:
    """Split a script into complete statements (``executescript`` would commit our transaction)."""
    statements, buffer = [], ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip() and not all(l.strip().startswith("--") or not l.strip() for l in buffer.splitlines()):
        raise ValueError(f"incomplete SQL statement at the end of a migration: {buffer.strip()[:80]!r}")
    return statements


def forget(db_path: Path) -> None:
    """Drop the "already migrated" memo for a path whose file was removed or replaced."""
    _ready.discard(str(Path(db_path).resolve()))


def ensure_schema(db_path: Path) -> int:
    """Apply any pending migrations; returns the schema version."""
    key = str(Path(db_path).resolve())
    if key in _ready:
        return latest_version()
    with _lock:
        if key in _ready:
            return latest_version()
        conn = connect(db_path)
        try:
            for number, path in migrations():
                conn.execute("BEGIN IMMEDIATE")  # also serializes two processes starting at once
                try:
                    if conn.execute("PRAGMA user_version").fetchone()[0] >= number:
                        conn.execute("ROLLBACK")
                        continue
                    for statement in _statements(path.read_text(encoding="utf-8")):
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version = {number}")
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        if version > latest_version():
            raise RuntimeError(f"{db_path} has schema version {version}, newer than this code ({latest_version()})")
        _ready.add(key)
        return version
