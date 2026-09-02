from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from os import PathLike

BUSY_TIMEOUT_MILLISECONDS = 5_000


def connect_database(database_path: str | PathLike[str]) -> sqlite3.Connection:
    """Open an independently owned connection with integrity checks enabled."""
    connection = sqlite3.connect(database_path, timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Generator[sqlite3.Connection]:
    """Provide an explicit transaction boundary with commit or rollback."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
