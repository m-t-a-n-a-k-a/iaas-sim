from __future__ import annotations

from os import PathLike

from iaas_sim.adapters.sqlite.connection import connect_database, transaction

SCHEMA_VERSION = 1

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
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
