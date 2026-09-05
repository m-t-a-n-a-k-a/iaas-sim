package dev.iaassim.application

import dev.iaassim.adapters.identity.InMemoryVirtualMachineIdentityAdapter
import dev.iaassim.domain.entity.virtualmachine.PowerState
import dev.iaassim.domain.entity.virtualmachine.PowerCommand
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

private val id = VirtualMachineId(UUID.fromString("01890f4c-7f15-7cc2-98c8-0800200c9a66"))
private val otherId = VirtualMachineId(UUID.fromString("01890f4c-7f15-7cc2-98c8-0800200c9a67"))
private val ref = BackendVirtualMachineRef("vm-1")

private class FakeVmPort(
    var listed: Outcome<List<ObservedVirtualMachine>, VirtualMachineBackendFailure> = Ok(emptyList()),
    var got: Outcome<ObservedVirtualMachine, VirtualMachineBackendError> =
        Err(VirtualMachineBackendNotFound(ref)),
) : VirtualMachinePort {
    override fun listVirtualMachines() = listed
    override fun getVirtualMachine(backendRef: BackendVirtualMachineRef) = got
    override fun submitPowerCommand(backendRef: BackendVirtualMachineRef, command: PowerCommand):
        Outcome<BackendOperationRef, PowerCommandBackendSubmissionFailure> = Ok(BackendOperationRef("task-1"))
}

class VirtualMachineReadTest {
    @Test fun `list adopts markerless VM and projects backend state`() {
        val identity = InMemoryVirtualMachineIdentityAdapter()
        val port = FakeVmPort(Ok(listOf(ObservedVirtualMachine(ref, "vm", PowerState.RUNNING))))
        val result = assertIs<Ok<List<dev.iaassim.domain.entity.virtualmachine.VirtualMachine>>>(listVirtualMachines(port, identity))
        assertEquals("vm", result.value.single().name)
        assertEquals(PowerState.RUNNING, result.value.single().powerState)
        assertEquals(ref, assertIs<Ok<BackendVirtualMachineRef>>(identity.getBackendRef(result.value.single().id)).value)
    }

    @Test fun `list includes matching marker and skips unmapped marker`() {
        val identity = InMemoryVirtualMachineIdentityAdapter()
        val mapped = assertIs<Ok<VirtualMachineId>>(identity.getOrCreateByBackendRef(ref)).value
        val observations = listOf(
            ObservedVirtualMachine(ref, "mapped", PowerState.STOPPED, mapped),
            ObservedVirtualMachine(BackendVirtualMachineRef("vm-2"), "pending", PowerState.STOPPED, id),
        )
        val result = assertIs<Ok<List<dev.iaassim.domain.entity.virtualmachine.VirtualMachine>>>(
            listVirtualMachines(FakeVmPort(Ok(observations)), identity),
        )
        assertEquals(listOf("mapped"), result.value.map { it.name })
    }

    @Test fun `list rejects mismatched marker and propagates backend failure`() {
        val identity = InMemoryVirtualMachineIdentityAdapter()
        identity.getOrCreateByBackendRef(ref)
        assertIs<Err<VirtualMachineIdentityPersistenceFailure>>(
            listVirtualMachines(FakeVmPort(Ok(listOf(ObservedVirtualMachine(ref, "vm", PowerState.STOPPED, id)))), identity),
        )
        assertIs<Err<VirtualMachineBackendFailure>>(
            listVirtualMachines(FakeVmPort(Err(VirtualMachineBackendFailure("list", "down"))), identity),
        )
    }

    @Test fun `get projects success and accepts matching marker`() {
        val identity = InMemoryVirtualMachineIdentityAdapter()
        val mapped = assertIs<Ok<VirtualMachineId>>(identity.getOrCreateByBackendRef(ref)).value
        val observed = ObservedVirtualMachine(ref, "vm", PowerState.RUNNING, mapped)
        val result = assertIs<Ok<dev.iaassim.domain.entity.virtualmachine.VirtualMachine>>(
            getVirtualMachine(FakeVmPort(got = Ok(observed)), identity, mapped),
        )
        assertEquals(mapped, result.value.id)
    }

    @Test fun `get translates both not found sources and propagates backend failure`() {
        val identity = InMemoryVirtualMachineIdentityAdapter()
        assertIs<Err<VirtualMachineNotFound>>(getVirtualMachine(FakeVmPort(), identity, id))
        val mapped = assertIs<Ok<VirtualMachineId>>(identity.getOrCreateByBackendRef(ref)).value
        assertIs<Err<VirtualMachineNotFound>>(getVirtualMachine(FakeVmPort(), identity, mapped))
        assertIs<Err<VirtualMachineBackendFailure>>(
            getVirtualMachine(FakeVmPort(got = Err(VirtualMachineBackendFailure("get", "down"))), identity, mapped),
        )
    }

    @Test fun `get rejects mismatched marker`() {
        val identity = InMemoryVirtualMachineIdentityAdapter()
        val mapped = assertIs<Ok<VirtualMachineId>>(identity.getOrCreateByBackendRef(ref)).value
        assertIs<Err<VirtualMachineIdentityPersistenceFailure>>(
            getVirtualMachine(FakeVmPort(got = Ok(ObservedVirtualMachine(ref, "vm", PowerState.STOPPED, otherId))), identity, mapped),
        )
    }
}

class InMemoryVirtualMachineIdentityAdapterTest {
    @Test fun `generates stable distinct UUIDv7 mappings and reverse lookup`() {
        val adapter = InMemoryVirtualMachineIdentityAdapter()
        val first = assertIs<Ok<VirtualMachineId>>(adapter.getOrCreateByBackendRef(ref)).value
        val again = assertIs<Ok<VirtualMachineId>>(adapter.getOrCreateByBackendRef(ref)).value
        val second = assertIs<Ok<VirtualMachineId>>(adapter.getOrCreateByBackendRef(BackendVirtualMachineRef("vm-2"))).value
        assertEquals(7, first.value.version())
        assertEquals(first, again)
        kotlin.test.assertNotEquals(first, second)
        assertEquals(ref, assertIs<Ok<BackendVirtualMachineRef>>(adapter.getBackendRef(first)).value)
        assertIs<Err<VirtualMachineIdentityNotFound>>(adapter.getBackendRef(id))
        assertNull(assertIs<Ok<VirtualMachineId?>>(adapter.findByBackendRef(BackendVirtualMachineRef("missing"))).value)
    }
}
