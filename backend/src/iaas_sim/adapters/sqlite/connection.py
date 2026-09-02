from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from os import PathLike

BUSY_TIMEOUT_MILLISECONDS = 5_000


@contextmanager
def connect_database(
    database_path: str | PathLike[str],
) -> Generator[sqlite3.Connection]:
    """Own a connection for the duration of a context manager scope."""
    connection = sqlite3.connect(database_path, timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")
        yield connection
    finally:
        connection.close()


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
