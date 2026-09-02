from __future__ import annotations

import sqlite3
from os import PathLike
from uuid import UUID, uuid7

from iaas_sim.adapters.sqlite.connection import connect_database, transaction
from iaas_sim.application.identity import (
    BackendVirtualMachineRef,
    VirtualMachineIdentityError,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
)
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Err, Ok, Result

UUID_VERSION_7 = 7


class SQLiteAdapter:
    def __init__(self, database_path: str | PathLike[str]) -> None:
        self._database_path = database_path

    def get_or_create_by_backend_ref(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[VirtualMachineId, VirtualMachineIdentityPersistenceFailure]:
        candidate = uuid7()
        try:
            with connect_database(self._database_path) as connection, transaction(connection):
                connection.execute(
                    """INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)
                    ON CONFLICT(backend_ref) DO NOTHING""",
                    (str(candidate), str(backend_ref)),
                )
                row = connection.execute(
                    "SELECT id FROM virtual_machine WHERE backend_ref = ?", (str(backend_ref),)
                ).fetchone()
            if row is None or not isinstance(row[0], str):
                return Err(
                    VirtualMachineIdentityPersistenceFailure("get-or-create", "mapping unavailable")
                )
            parsed = UUID(row[0])
            if parsed.version != UUID_VERSION_7:
                return Err(
                    VirtualMachineIdentityPersistenceFailure(
                        "get-or-create", "stored ID is not UUIDv7"
                    )
                )
            return Ok(VirtualMachineId(parsed))
        except (sqlite3.Error, ValueError) as exc:
            return Err(VirtualMachineIdentityPersistenceFailure("get-or-create", str(exc)))

    def get_backend_ref(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[BackendVirtualMachineRef, VirtualMachineIdentityError]:
        try:
            with connect_database(self._database_path) as connection:
                row = connection.execute(
                    "SELECT backend_ref FROM virtual_machine WHERE id = ?",
                    (str(virtual_machine_id),),
                ).fetchone()
            if row is None:
                return Err(VirtualMachineIdentityNotFound(virtual_machine_id))
            if not isinstance(row[0], str):
                return Err(
                    VirtualMachineIdentityPersistenceFailure("get", "invalid backend reference")
                )
            return Ok(BackendVirtualMachineRef(row[0]))
        except sqlite3.Error as exc:
            return Err(VirtualMachineIdentityPersistenceFailure("get", str(exc)))
