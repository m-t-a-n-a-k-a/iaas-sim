from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationPort,
    BackendOperationRunning,
    BackendOperationSucceeded,
    OperationNotFound,
    OperationPollingFailure,
    OperationRegistryPort,
)
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Running,
    Succeeded,
)
from iaas_sim.result import Err, Ok, Result

BACKEND_OPERATION_FAILURE_REASON = "Backend operation failed"


def get_operation(
    registry: OperationRegistryPort,
    backend: BackendOperationPort,
    operation_id: OperationId,
) -> Result[Operation, OperationNotFound | OperationPollingFailure]:
    tracked = registry.get(operation_id)
    if tracked is None:
        return Err(OperationNotFound(operation_id))

    polled = backend.get_operation_status(tracked.backend_ref)
    if isinstance(polled, Err):
        return Err(polled.error)

    match polled.value:
        case BackendOperationRunning():
            status = Running()
        case BackendOperationSucceeded():
            status = Succeeded()
        case BackendOperationFailed():
            status = Failed(OperationFailure(BACKEND_OPERATION_FAILURE_REASON))
    return Ok(Operation(tracked.id, tracked.target, tracked.action, status))
