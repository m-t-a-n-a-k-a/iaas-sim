from uuid import UUID

from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationPort,
    BackendOperationRunning,
    BackendOperationStatus,
    BackendOperationSucceeded,
    BackendVirtualMachineCreated,
    OperationNotFound,
    OperationPersistenceFailure,
    OperationPollingFailure,
    OperationStorePort,
    StoredOperation,
    VirtualMachineCreateFinalizerPort,
)
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Succeeded,
    is_terminal,
)
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Err, Ok, Result

BACKEND_OPERATION_FAILURE_REASON = "Backend operation failed"
type GetOperationError = OperationNotFound | OperationPersistenceFailure | OperationPollingFailure
UUID_VERSION_7 = 7


def get_operation(  # noqa: PLR0911
    store: OperationStorePort,
    backend: BackendOperationPort,
    operation_id: OperationId,
    finalizer: VirtualMachineCreateFinalizerPort | None = None,
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
        case BackendOperationSucceeded(result):
            if (
                stored.operation.target.resource_type == "virtualMachines"
                and stored.operation.action == "CREATE"
            ):
                if not isinstance(result, BackendVirtualMachineCreated) or finalizer is None:
                    return Err(OperationPollingFailure("VM create result unavailable"))
                try:
                    target_id = UUID(stored.operation.target.resource_id)
                except ValueError:
                    return Err(OperationPersistenceFailure("reconcile", "invalid VM create target"))
                if target_id.version != UUID_VERSION_7:
                    return Err(
                        OperationPersistenceFailure("reconcile", "VM create target is not UUIDv7")
                    )
                finalized = finalizer.finalize_virtual_machine_create(
                    stored.operation, VirtualMachineId(target_id), result.backend_ref
                )
                if isinstance(finalized, Err):
                    return Err[GetOperationError](finalized.error)
                return finalized
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
