from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationNotFound,
    OperationPersistenceFailure,
    OperationStoreError,
    StoredOperation,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, Running, is_terminal
from iaas_sim.result import Err, Ok, Result


class InMemoryOperationStore:
    """Faithful test fake for persistent Operation Store semantics."""

    def __init__(self) -> None:
        self._operations: dict[OperationId, StoredOperation] = {}

    def create_running(
        self, operation: Operation, backend_ref: BackendOperationRef
    ) -> Result[Operation, OperationPersistenceFailure]:
        if not isinstance(operation.status, Running):
            return Err(OperationPersistenceFailure("create", "operation is not running"))
        if operation.id in self._operations:
            return Err(OperationPersistenceFailure("create", "operation already exists"))
        self._operations[operation.id] = StoredOperation(operation, backend_ref)
        return Ok(operation)

    def get(self, operation_id: OperationId) -> Result[StoredOperation, OperationStoreError]:
        stored = self._operations.get(operation_id)
        return Err(OperationNotFound(operation_id)) if stored is None else Ok(stored)

    def complete(
        self, operation: Operation
    ) -> Result[Operation, OperationNotFound | OperationPersistenceFailure]:
        stored = self._operations.get(operation.id)
        if stored is None:
            return Err(OperationNotFound(operation.id))
        if is_terminal(stored.operation.status):
            return Ok(stored.operation)
        if not is_terminal(operation.status):
            return Err(OperationPersistenceFailure("complete", "status is not terminal"))
        self._operations[operation.id] = StoredOperation(operation, stored.backend_ref)
        return Ok(operation)
