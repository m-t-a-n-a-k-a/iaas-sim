from __future__ import annotations

import sqlite3
from os import PathLike
from uuid import UUID

from iaas_sim.adapters.sqlite.connection import connect_database, transaction
from iaas_sim.application.identity import BackendVirtualMachineRef
from iaas_sim.application.operation import OperationPersistenceFailure
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Running,
    Succeeded,
)
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result

UUID_VERSION_7 = 7
OPERATION_COLUMN_COUNT = 6


class SQLiteVirtualMachineCreateFinalizer:
    """Atomically bind a created VM and complete its RUNNING Operation."""

    def __init__(self, database_path: str | PathLike[str]) -> None:
        self._database_path = database_path

    def finalize_virtual_machine_create(  # noqa: PLR0911
        self,
        operation: Operation,
        virtual_machine_id: VirtualMachineId,
        backend_ref: BackendVirtualMachineRef,
    ) -> Result[Operation, OperationPersistenceFailure]:
        try:
            with connect_database(self._database_path) as connection, transaction(connection):
                row = connection.execute(
                    """SELECT id, target_resource_type, target_resource_id, action,
                    state, failure_reason FROM operation WHERE id = ?""",
                    (str(operation.id),),
                ).fetchone()
                decoded = self._decode(row)
                if isinstance(decoded, Err):
                    return decoded
                current = decoded.value

                if isinstance(current.status, Failed):
                    return Ok(current)

                if isinstance(current.status, Succeeded):
                    if not self._has_exact_mapping(connection, virtual_machine_id, backend_ref):
                        return Err(
                            OperationPersistenceFailure(
                                "finalize-vm-create",
                                "SUCCEEDED VM create requires exact identity mapping",
                            )
                        )
                    return Ok(current)

                mapping_error = self._check_running_mapping(
                    connection, virtual_machine_id, backend_ref
                )
                if mapping_error is not None:
                    return Err(mapping_error)

                connection.execute(
                    """INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)
                    ON CONFLICT DO NOTHING""",
                    (str(virtual_machine_id), str(backend_ref)),
                )
                succeeded = Operation(current.id, current.target, current.action, Succeeded())
                cursor = connection.execute(
                    """UPDATE operation SET state = 'SUCCEEDED', failure_reason = NULL
                    WHERE id = ? AND state = 'RUNNING'""",
                    (str(current.id),),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError("operation transition conflict")
                return Ok(succeeded)
        except sqlite3.Error as exc:
            return Err(OperationPersistenceFailure("finalize-vm-create", str(exc)))

    @staticmethod
    def _has_exact_mapping(
        connection: sqlite3.Connection,
        virtual_machine_id: VirtualMachineId,
        backend_ref: BackendVirtualMachineRef,
    ) -> bool:
        by_id = connection.execute(
            "SELECT backend_ref FROM virtual_machine WHERE id = ?", (str(virtual_machine_id),)
        ).fetchone()
        by_ref = connection.execute(
            "SELECT id FROM virtual_machine WHERE backend_ref = ?", (str(backend_ref),)
        ).fetchone()
        return by_id == (str(backend_ref),) and by_ref == (str(virtual_machine_id),)

    @classmethod
    def _check_running_mapping(
        cls,
        connection: sqlite3.Connection,
        virtual_machine_id: VirtualMachineId,
        backend_ref: BackendVirtualMachineRef,
    ) -> OperationPersistenceFailure | None:
        by_id = connection.execute(
            "SELECT backend_ref FROM virtual_machine WHERE id = ?", (str(virtual_machine_id),)
        ).fetchone()
        by_ref = connection.execute(
            "SELECT id FROM virtual_machine WHERE backend_ref = ?", (str(backend_ref),)
        ).fetchone()
        if by_id is None and by_ref is None:
            return None
        if cls._has_exact_mapping(connection, virtual_machine_id, backend_ref):
            return None
        return OperationPersistenceFailure("finalize-vm-create", "VM identity mapping conflict")

    @staticmethod
    def _decode(row: tuple[object, ...] | None) -> Result[Operation, OperationPersistenceFailure]:
        if row is None or len(row) != OPERATION_COLUMN_COUNT:
            return Err(OperationPersistenceFailure("finalize-vm-create", "operation unavailable"))
        raw_id, resource_type, resource_id, action, state, reason = row
        if not (
            isinstance(raw_id, str)
            and isinstance(resource_type, str)
            and isinstance(resource_id, str)
            and isinstance(action, str)
            and isinstance(state, str)
        ):
            return Err(OperationPersistenceFailure("finalize-vm-create", "invalid operation"))
        try:
            parsed = UUID(raw_id)
        except ValueError as exc:
            return Err(OperationPersistenceFailure("finalize-vm-create", str(exc)))
        if parsed.version != UUID_VERSION_7:
            return Err(
                OperationPersistenceFailure("finalize-vm-create", "operation ID is not UUIDv7")
            )
        if state == "RUNNING" and reason is None:
            status = Running()
        elif state == "SUCCEEDED" and reason is None:
            status = Succeeded()
        elif state == "FAILED" and isinstance(reason, str):
            status = Failed(OperationFailure(reason))
        else:
            return Err(OperationPersistenceFailure("finalize-vm-create", "invalid operation state"))
        return Ok(
            Operation(
                OperationId(parsed), ResourceReference(resource_type, resource_id), action, status
            )
        )
