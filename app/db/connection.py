"""The one place that opens the application database (``data/app.db``).

Every store goes through ``transaction``: a short-lived connection with
foreign keys on, WAL journaling and a busy timeout, wrapped in an explicit
``BEGIN``/``COMMIT`` and always closed. ``immediate=True`` takes the write
lock up front, for read-then-write sequences such as "next version + insert".

The operational log database (``data/logs/logs.db``) is separate and keeps
its own long-lived connection in ``app.core.logging_config``.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BUSY_TIMEOUT_MS = 5000


def connect(path: Path) -> sqlite3.Connection:
    """An autocommit connection (``isolation_level=None``); ``transaction`` adds the BEGIN/COMMIT."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(path: Path, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """One transaction on a fresh connection: committed on success, rolled back on error, always closed."""
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()
