package dev.iaassim.adapters.sqlite

import dev.iaassim.application.*
import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.operation.*
import dev.iaassim.result.*
import java.sql.DriverManager
import java.util.UUID
import kotlin.io.path.createTempDirectory
import kotlin.test.*

class SQLiteOperationStoreTest {
    private val id = OperationId(UUID.fromString("0198f5d0-7300-7000-8000-000000000002"))
    private fun operation(status: OperationStatus) = Operation(id, ResourceReference("virtualMachines", "vm-id"), "STOP", status)

    @Test fun `schema persists running and backend ref across store recreation`() {
        val path = createTempDirectory().resolve("operations.db")
        val store1 = SQLiteOperationStore(path)
        assertEquals(operation(Running), assertIs<Ok<Operation>>(store1.createRunning(operation(Running), BackendOperationRef("task-1"))).value)
        val stored = assertIs<Ok<StoredOperation>>(SQLiteOperationStore(path).get(id)).value
        assertEquals(BackendOperationRef("task-1"), stored.backendRef); assertEquals(7, stored.operation.id.value.version())
    }
    @Test fun `completion is one-way and idempotent for succeeded and failed`() {
        listOf(Succeeded, Failed(OperationFailure("failed"))).forEachIndexed { index, terminal ->
            val localId = OperationId(UUID.fromString("0198f5d0-7300-7000-8000-00000000000${index + 3}"))
            val path = createTempDirectory().resolve("operations.db"); val store = SQLiteOperationStore(path)
            val running = Operation(localId, ResourceReference("virtualMachines", "vm"), "START", Running)
            assertIs<Ok<Operation>>(store.createRunning(running, BackendOperationRef("task")))
            val completed = running.copy(status = terminal)
            assertEquals(terminal, assertIs<Ok<Operation>>(store.complete(completed)).value.status)
            assertEquals(terminal, assertIs<Ok<Operation>>(store.complete(completed)).value.status)
        }
    }
    @Test fun `rejects invalid transitions unknown ids duplicates and malformed UUID`() {
        val path = createTempDirectory().resolve("operations.db"); val store = SQLiteOperationStore(path)
        assertIs<Err<OperationPersistenceFailure>>(store.createRunning(operation(Succeeded), BackendOperationRef("task")))
        assertIs<Err<OperationPersistenceFailure>>(store.complete(operation(Running)))
        assertIs<Err<OperationNotFound>>(store.get(id))
        assertIs<Ok<Operation>>(store.createRunning(operation(Running), BackendOperationRef("task")))
        assertIs<Err<OperationPersistenceFailure>>(store.createRunning(operation(Running), BackendOperationRef("task")))
        val malformed = UUID.fromString("00000000-0000-4000-8000-000000000000")
        DriverManager.getConnection("jdbc:sqlite:${path.toAbsolutePath()}").use { connection ->
            connection.createStatement().executeUpdate("INSERT INTO operation VALUES ('$malformed', 'virtualMachines', 'vm', 'START', 'RUNNING', NULL, 'task')")
        }
        assertIs<Err<OperationPersistenceFailure>>(store.get(OperationId(malformed)))
    }
}
