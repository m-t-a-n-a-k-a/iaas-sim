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
from iaas_sim.result import Err, Ok, Result

BACKEND_OPERATION_FAILURE_REASON = "Backend operation failed"
type GetOperationError = OperationNotFound | OperationPersistenceFailure | OperationPollingFailure


def get_operation(
    store: OperationStorePort, backend: BackendOperationPort, operation_id: OperationId
) -> Result[Operation, GetOperationError]:
    loaded = store.get(operation_id)
    if isinstance(loaded, Err):
        return Err[GetOperationError](loaded.error)
    stored: StoredOperation = loaded.value

    if is_terminal(stored.operation.status):
        return Ok(stored.operation)

    polled = backend.get_operation_status(stored.backend_ref)
    if isinstance(polled, Err):
        return Err[GetOperationError](polled.error)

    status: BackendOperationStatus = polled.value
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

    completed = store.complete(terminal)
    if isinstance(completed, Err):
        return Err[GetOperationError](completed.error)
    return completed
