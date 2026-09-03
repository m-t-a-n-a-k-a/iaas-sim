from __future__ import annotations

from os import PathLike
from uuid import uuid7

from iaas_sim.adapters.sqlite.connection import connect_database, transaction

SCHEMA_VERSION = 3
PREVIOUS_SCHEMA_VERSION = 2

_VERSION_1_STATEMENTS = (
    """CREATE TABLE virtual_machine (
    id TEXT PRIMARY KEY,
    backend_ref TEXT NOT NULL UNIQUE
) STRICT""",
    """CREATE TABLE snapshot (
    id TEXT PRIMARY KEY,
    backend_ref TEXT NOT NULL UNIQUE,
    virtual_machine_id TEXT NOT NULL,
    FOREIGN KEY (virtual_machine_id) REFERENCES virtual_machine(id)
) STRICT""",
    """CREATE INDEX snapshot_virtual_machine_id_idx
    ON snapshot (virtual_machine_id)""",
)

_VERSION_2_STATEMENTS = (
    """CREATE TABLE operation (
    id TEXT PRIMARY KEY,
    target_resource_type TEXT NOT NULL,
    target_resource_id TEXT NOT NULL,
    action TEXT NOT NULL,
    state TEXT NOT NULL,
    failure_reason TEXT,
    backend_ref TEXT NOT NULL,
    CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    CHECK ((state = 'FAILED' AND failure_reason IS NOT NULL)
        OR (state <> 'FAILED' AND failure_reason IS NULL))
) STRICT""",
)

_VERSION_3_STATEMENTS = (
    """CREATE TABLE instance_type (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    vcpus INTEGER NOT NULL CHECK (vcpus > 0),
    memory_mib INTEGER NOT NULL CHECK (memory_mib > 0)
) STRICT""",
)

_INITIAL_INSTANCE_TYPES = (
    ("small", 1, 1024),
    ("medium", 2, 2048),
    ("large", 4, 4096),
)


def migrate_database(database_path: str | PathLike[str]) -> None:
    """Upgrade a database to the current schema version transactionally."""
    with connect_database(database_path) as connection:
        current_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema version {current_version} is newer than supported "
                f"version {SCHEMA_VERSION}"
            )
        if current_version == 0:
            with transaction(connection):
                for statement in _VERSION_1_STATEMENTS:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 1")
            current_version = 1
        if current_version == 1:
            with transaction(connection):
                for statement in _VERSION_2_STATEMENTS:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 2")
            current_version = 2
        if current_version == PREVIOUS_SCHEMA_VERSION:
            with transaction(connection):
                for statement in _VERSION_3_STATEMENTS:
                    connection.execute(statement)
                connection.executemany(
                    "INSERT INTO instance_type (id, name, vcpus, memory_mib) VALUES (?, ?, ?, ?)",
                    (
                        (str(uuid7()), name, vcpus, memory_mib)
                        for name, vcpus, memory_mib in _INITIAL_INSTANCE_TYPES
                    ),
                )
                connection.execute("PRAGMA user_version = 3")
