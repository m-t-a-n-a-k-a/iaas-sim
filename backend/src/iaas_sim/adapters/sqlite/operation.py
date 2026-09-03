from __future__ import annotations

import sqlite3
from os import PathLike
from uuid import UUID

from iaas_sim.adapters.sqlite.connection import connect_database, transaction
from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationNotFound,
    OperationPersistenceFailure,
    OperationStoreError,
    StoredOperation,
)
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Running,
    Succeeded,
)
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result

UUID_VERSION_7 = 7
OPERATION_COLUMN_COUNT = 7


class SQLiteOperationStore:
    def __init__(self, database_path: str | PathLike[str]) -> None:
        self._database_path = database_path

    def create_running(
        self, operation: Operation, backend_ref: BackendOperationRef
    ) -> Result[Operation, OperationPersistenceFailure]:
        if not isinstance(operation.status, Running):
            return Err(OperationPersistenceFailure("create", "operation is not running"))
        try:
            with connect_database(self._database_path) as connection, transaction(connection):
                connection.execute(
                    """INSERT INTO operation
                    (id, target_resource_type, target_resource_id, action, state,
                     failure_reason, backend_ref)
                    VALUES (?, ?, ?, ?, 'RUNNING', NULL, ?)""",
                    (
                        str(operation.id),
                        operation.target.resource_type,
                        operation.target.resource_id,
                        operation.action,
                        str(backend_ref),
                    ),
                )
            return Ok(operation)
        except sqlite3.Error as exc:
            return Err(OperationPersistenceFailure("create", str(exc)))

    def get(self, operation_id: OperationId) -> Result[StoredOperation, OperationStoreError]:
        try:
            with connect_database(self._database_path) as connection:
                row = connection.execute(
                    """SELECT id, target_resource_type, target_resource_id, action,
                    state, failure_reason, backend_ref FROM operation WHERE id = ?""",
                    (str(operation_id),),
                ).fetchone()
            if row is None:
                return Err(OperationNotFound(operation_id))
            decoded = self._decode(row)
            if isinstance(decoded, Err):
                return Err(decoded.error)
            return Ok(decoded.value)
        except sqlite3.Error as exc:
            return Err(OperationPersistenceFailure("get", str(exc)))

    def complete(self, operation: Operation) -> Result[Operation, OperationStoreError]:
        if isinstance(operation.status, Succeeded):
            state, failure_reason = "SUCCEEDED", None
        elif isinstance(operation.status, Failed):
            state, failure_reason = "FAILED", operation.status.failure.reason
        else:
            return Err(OperationPersistenceFailure("complete", "status is not terminal"))
        try:
            with connect_database(self._database_path) as connection, transaction(connection):
                cursor = connection.execute(
                    """UPDATE operation SET state = ?, failure_reason = ?
                    WHERE id = ? AND state = 'RUNNING'""",
                    (state, failure_reason, str(operation.id)),
                )
                if cursor.rowcount == 1:
                    return Ok(operation)
                row = connection.execute(
                    """SELECT id, target_resource_type, target_resource_id, action,
                    state, failure_reason, backend_ref FROM operation WHERE id = ?""",
                    (str(operation.id),),
                ).fetchone()
                if row is None:
                    return Err(OperationNotFound(operation.id))
                decoded = self._decode(row)
                if isinstance(decoded, Err):
                    return Err(decoded.error)
                return Ok(decoded.value.operation)
        except sqlite3.Error as exc:
            return Err(OperationPersistenceFailure("complete", str(exc)))

    @staticmethod
    def _decode(row: tuple[object, ...]) -> Result[StoredOperation, OperationPersistenceFailure]:
        if len(row) != OPERATION_COLUMN_COUNT:
            return Err(OperationPersistenceFailure("decode", "invalid stored operation"))
        raw_id, resource_type, resource_id, action, state, reason, backend_ref = row
        if not (
            isinstance(raw_id, str)
            and isinstance(resource_type, str)
            and isinstance(resource_id, str)
            and isinstance(action, str)
            and isinstance(state, str)
            and isinstance(backend_ref, str)
        ):
            return Err(OperationPersistenceFailure("decode", "invalid stored operation"))
        try:
            parsed = UUID(raw_id)
        except ValueError as exc:
            return Err(OperationPersistenceFailure("decode", str(exc)))
        if parsed.version != UUID_VERSION_7:
            return Err(OperationPersistenceFailure("decode", "stored ID is not UUIDv7"))
        if state == "RUNNING" and reason is None:
            status = Running()
        elif state == "SUCCEEDED" and reason is None:
            status = Succeeded()
        elif state == "FAILED" and isinstance(reason, str):
            status = Failed(OperationFailure(reason))
        else:
            return Err(OperationPersistenceFailure("decode", "invalid stored status"))
        operation = Operation(
            OperationId(parsed), ResourceReference(resource_type, resource_id), action, status
        )
        return Ok(StoredOperation(operation, BackendOperationRef(backend_ref)))
