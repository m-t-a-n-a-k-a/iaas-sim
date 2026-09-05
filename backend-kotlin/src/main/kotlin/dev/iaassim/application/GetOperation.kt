package dev.iaassim.application

import dev.iaassim.domain.entity.operation.Failed
import dev.iaassim.domain.entity.operation.Operation
import dev.iaassim.domain.entity.operation.OperationFailure
import dev.iaassim.domain.entity.operation.OperationId
import dev.iaassim.domain.entity.operation.Succeeded
import dev.iaassim.domain.entity.operation.isTerminal
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome

fun getOperation(store: OperationStorePort, backend: BackendOperationPort, operationId: OperationId):
    Outcome<Operation, GetOperationError> {
    val stored = when (val result = store.get(operationId)) {
        is Ok -> result.value
        is Err -> return when (val error = result.error) {
            is OperationNotFound -> Err(error)
            is OperationPersistenceFailure -> Err(error)
        }
    }
    if (isTerminal(stored.operation.status)) return Ok(stored.operation)
    val terminal = when (val result = backend.getOperationStatus(stored.backendRef)) {
        is Err -> return Err(result.error)
        is Ok -> when (result.value) {
            BackendOperationRunning -> return Ok(stored.operation)
            BackendOperationSucceeded -> stored.operation.copy(status = Succeeded)
            is BackendOperationFailed -> stored.operation.copy(status = Failed(OperationFailure("Backend operation failed")))
        }
    }
    return when (val result = store.complete(terminal)) {
        is Ok -> result
        is Err -> when (val error = result.error) {
            is OperationNotFound -> Err(error)
            is OperationPersistenceFailure -> Err(error)
        }
    }
}
