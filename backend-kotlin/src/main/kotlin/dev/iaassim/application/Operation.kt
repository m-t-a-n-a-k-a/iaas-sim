package dev.iaassim.application

import dev.iaassim.domain.entity.operation.Operation
import dev.iaassim.domain.entity.operation.OperationId
import dev.iaassim.result.Outcome

@JvmInline value class BackendOperationRef(val value: String)
sealed interface BackendOperationStatus
data object BackendOperationRunning : BackendOperationStatus
sealed interface BackendOperationResult
data class BackendVirtualMachineCreated(val backendRef: BackendVirtualMachineRef) : BackendOperationResult
data class BackendOperationSucceeded(val result: BackendOperationResult? = null) : BackendOperationStatus
data class BackendOperationFailed(val reason: String) : BackendOperationStatus

data class OperationNotFound(val operationId: OperationId) : OperationStoreError, GetOperationError
data class OperationPersistenceFailure(val operation: String, val reason: String) : OperationStoreError, GetOperationError
data class OperationPollingFailure(val reason: String) : GetOperationError
sealed interface OperationStoreError
sealed interface GetOperationError
data class StoredOperation(val operation: Operation, val backendRef: BackendOperationRef)

interface OperationStorePort {
    fun createRunning(operation: Operation, backendRef: BackendOperationRef): Outcome<Operation, OperationPersistenceFailure>
    fun get(operationId: OperationId): Outcome<StoredOperation, OperationStoreError>
    fun complete(operation: Operation): Outcome<Operation, OperationStoreError>
}

interface BackendOperationPort {
    fun getOperationStatus(backendRef: BackendOperationRef): Outcome<BackendOperationStatus, OperationPollingFailure>
}

interface VirtualMachineCreateFinalizerPort {
    fun finalizeVirtualMachineCreate(operation: Operation, virtualMachineId: dev.iaassim.domain.entity.virtualmachine.VirtualMachineId,
        backendRef: BackendVirtualMachineRef): Outcome<Operation, OperationPersistenceFailure>
}
