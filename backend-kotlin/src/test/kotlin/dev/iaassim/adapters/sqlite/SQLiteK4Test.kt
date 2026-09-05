package dev.iaassim.adapters.sqlite

import dev.iaassim.application.*
import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.instancetype.InstanceTypeId
import dev.iaassim.domain.entity.operation.*
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.*
import java.sql.DriverManager
import java.util.UUID
import kotlin.io.path.createTempDirectory
import kotlin.test.*

class SQLiteK4Test {
    @Test fun `identity is UUIDv7 bidirectional durable and missing is typed`() {
        val path = createTempDirectory().resolve("k4.db"); val ref = BackendVirtualMachineRef("vm-1")
        val first = assertIs<Ok<VirtualMachineId>>(SQLiteVirtualMachineIdentityAdapter(path).getOrCreateByBackendRef(ref)).value
        assertEquals(7, first.value.version())
        val restarted = SQLiteVirtualMachineIdentityAdapter(path)
        assertEquals(first, assertIs<Ok<VirtualMachineId>>(restarted.getOrCreateByBackendRef(ref)).value)
        assertEquals(ref, assertIs<Ok<BackendVirtualMachineRef>>(restarted.getBackendRef(first)).value)
        assertNull(assertIs<Ok<VirtualMachineId?>>(restarted.findByBackendRef(BackendVirtualMachineRef("missing"))).value)
        assertIs<Err<VirtualMachineIdentityNotFound>>(restarted.getBackendRef(VirtualMachineId(UUID.fromString("0198f5d0-7300-7000-8000-000000000099"))))
    }

    @Test fun `instance types seed once with stable UUIDv7 IDs and deterministic sizing`() {
        val path = createTempDirectory().resolve("k4.db")
        val first = assertIs<Ok<List<dev.iaassim.domain.entity.instancetype.InstanceType>>>(SQLiteInstanceTypeStore(path).listInstanceTypes()).value
        assertEquals(listOf("large", "medium", "small"), first.map { it.name })
        assertEquals(listOf(4 to 4096, 2 to 2048, 1 to 1024), first.map { it.vcpus to it.memoryMiB })
        assertTrue(first.all { it.id.value.version() == 7 })
        assertEquals(first, assertIs<Ok<List<dev.iaassim.domain.entity.instancetype.InstanceType>>>(SQLiteInstanceTypeStore(path).listInstanceTypes()).value)
        assertEquals(first.first(), assertIs<Ok<dev.iaassim.domain.entity.instancetype.InstanceType>>(
            SQLiteInstanceTypeStore(path).getInstanceType(first.first().id)).value)
        assertIs<Err<InstanceTypeNotFound>>(SQLiteInstanceTypeStore(path).getInstanceType(
            InstanceTypeId(UUID.fromString("0198f5d0-7300-7000-8000-000000000099"))))
    }

    @Test fun `create finalization commits exact identity and success atomically`() {
        val path = createTempDirectory().resolve("k4.db"); val store = SQLiteOperationStore(path)
        val operation = Operation(OperationId(UUID.fromString("0198f5d0-7300-7000-8000-000000000001")),
            ResourceReference("virtualMachines", "0198f5d0-7300-7000-8000-000000000002"), "CREATE", Running)
        assertIs<Ok<Operation>>(store.createRunning(operation, BackendOperationRef("task-1")))
        val vmId = VirtualMachineId(UUID.fromString(operation.target.id)); val backend = BackendVirtualMachineRef("vm-20")
        assertEquals(Succeeded, assertIs<Ok<Operation>>(SQLiteVirtualMachineCreateFinalizer(path)
            .finalizeVirtualMachineCreate(operation, vmId, backend)).value.status)
        assertEquals(backend, assertIs<Ok<BackendVirtualMachineRef>>(SQLiteVirtualMachineIdentityAdapter(path).getBackendRef(vmId)).value)
        assertEquals(Succeeded, assertIs<Ok<StoredOperation>>(store.get(operation.id)).value.operation.status)
    }

    @Test fun `conflicting finalization rolls back and leaves operation running`() {
        val path = createTempDirectory().resolve("k4.db"); val store = SQLiteOperationStore(path)
        val id = VirtualMachineId(UUID.fromString("0198f5d0-7300-7000-8000-000000000002"))
        val operation = Operation(OperationId(UUID.fromString("0198f5d0-7300-7000-8000-000000000001")),
            ResourceReference("virtualMachines", id.value.toString()), "CREATE", Running)
        assertIs<Ok<Operation>>(store.createRunning(operation, BackendOperationRef("task")))
        DriverManager.getConnection("jdbc:sqlite:${path.toAbsolutePath()}").use { it.createStatement().executeUpdate(
            "INSERT INTO virtual_machine VALUES ('${id.value}', 'vm-other')") }
        assertIs<Err<OperationPersistenceFailure>>(SQLiteVirtualMachineCreateFinalizer(path)
            .finalizeVirtualMachineCreate(operation, id, BackendVirtualMachineRef("vm-created")))
        assertEquals(Running, assertIs<Ok<StoredOperation>>(store.get(operation.id)).value.operation.status)
    }
}
