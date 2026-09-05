package dev.iaassim.application

import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.operation.*
import dev.iaassim.result.*
import java.util.UUID
import kotlin.test.*

private val operationId = OperationId(UUID.fromString("0198f5d0-7300-7000-8000-000000000001"))
private fun operation(status: OperationStatus) = Operation(operationId, ResourceReference("virtualMachines", "vm"), "START", status)
private class OperationFakeStore(var stored: Outcome<StoredOperation, OperationStoreError>, var completionFailure: Boolean = false) : OperationStorePort {
    var completes = 0
    override fun createRunning(operation: Operation, backendRef: BackendOperationRef) = Ok(operation)
    override fun get(operationId: OperationId) = stored
    override fun complete(operation: Operation): Outcome<Operation, OperationStoreError> { completes++
        return if (completionFailure) Err(OperationPersistenceFailure("complete", "down")) else Ok(operation) }
}
private class OperationFakeBackend(var status: Outcome<BackendOperationStatus, OperationPollingFailure>) : BackendOperationPort {
    var polls = 0
    override fun getOperationStatus(backendRef: BackendOperationRef): Outcome<BackendOperationStatus, OperationPollingFailure> { polls++; return status }
}

class OperationApplicationTest {
    @Test fun `terminal states are not polled`() {
        listOf(Succeeded, Failed(OperationFailure("public"))).forEach { terminal ->
            val store = OperationFakeStore(Ok(StoredOperation(operation(terminal), BackendOperationRef("secret"))))
            val backend = OperationFakeBackend(Ok(BackendOperationRunning))
            assertEquals(terminal, assertIs<Ok<Operation>>(getOperation(store, backend, operationId)).value.status)
            assertEquals(0, backend.polls)
        }
    }
    @Test fun `running polling decision table persists only terminal sanitized results`() {
        val cases = listOf(BackendOperationRunning to Running, BackendOperationSucceeded() to Succeeded,
            BackendOperationFailed("vcenter secret") to Failed(OperationFailure("Backend operation failed")))
        cases.forEach { (backendStatus, expected) ->
            val store = OperationFakeStore(Ok(StoredOperation(operation(Running), BackendOperationRef("task-secret"))))
            val result = assertIs<Ok<Operation>>(getOperation(store, OperationFakeBackend(Ok(backendStatus)), operationId)).value
            assertEquals(expected, result.status); assertEquals(if (expected == Running) 0 else 1, store.completes)
        }
    }
    @Test fun `not found polling and completion failures remain exact typed errors`() {
        val missing = OperationFakeStore(Err(OperationNotFound(operationId)))
        assertIs<Err<OperationNotFound>>(getOperation(missing, OperationFakeBackend(Ok(BackendOperationRunning)), operationId))
        val running = Ok(StoredOperation(operation(Running), BackendOperationRef("task")))
        assertIs<Err<OperationPollingFailure>>(getOperation(OperationFakeStore(running),
            OperationFakeBackend(Err(OperationPollingFailure("down"))), operationId))
        assertIs<Err<OperationPersistenceFailure>>(getOperation(OperationFakeStore(running, true),
            OperationFakeBackend(Ok(BackendOperationSucceeded())), operationId))
    }
}
