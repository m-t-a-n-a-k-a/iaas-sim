from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationPort,
    BackendOperationRunning,
    BackendOperationStatus,
    BackendOperationSucceeded,
    OperationNotFound,
    OperationPersistenceFailure,
    OperationPollingFailure,
    OperationStorePort,
    StoredOperation,
)
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Succeeded,
    is_terminal,
)
from iaas_sim.result import Ok, Result, and_then, map_error

BACKEND_OPERATION_FAILURE_REASON = "Backend operation failed"
type GetOperationError = OperationNotFound | OperationPersistenceFailure | OperationPollingFailure


def _as_get_operation_error(error: GetOperationError) -> GetOperationError:
    return error


def get_operation(
    store: OperationStorePort, backend: BackendOperationPort, operation_id: OperationId
) -> Result[Operation, GetOperationError]:
    def poll(stored: StoredOperation) -> Result[Operation, GetOperationError]:
        if is_terminal(stored.operation.status):
            return Ok(stored.operation)

        def reconcile(status: BackendOperationStatus) -> Result[Operation, GetOperationError]:
            match status:
                case BackendOperationRunning():
                    return Ok(stored.operation)
                case BackendOperationSucceeded():
                    terminal = Operation(
                        stored.operation.id,
                        stored.operation.target,
                        stored.operation.action,
                        Succeeded(),
                    )
                case BackendOperationFailed():
                    terminal = Operation(
                        stored.operation.id,
                        stored.operation.target,
                        stored.operation.action,
                        Failed(OperationFailure(BACKEND_OPERATION_FAILURE_REASON)),
                    )
            return map_error(store.complete(terminal), _as_get_operation_error)

        return and_then(backend.get_operation_status(stored.backend_ref), reconcile)

    return and_then(store.get(operation_id), poll)
