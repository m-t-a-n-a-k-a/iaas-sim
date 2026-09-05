package dev.iaassim.adapters.vsphere

import dev.iaassim.result.Ok
import dev.iaassim.application.BackendOperationRunning
import dev.iaassim.application.BackendOperationSucceeded
import dev.iaassim.domain.entity.virtualmachine.PowerCommand
import dev.iaassim.domain.entity.virtualmachine.PowerState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlin.test.fail
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable
import com.github.f4b6a3.uuid.UuidCreator
import dev.iaassim.adapters.sqlite.*
import dev.iaassim.application.*
import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.operation.*
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId

@EnabledIfEnvironmentVariable(named = "VSPHERE_SMOKE", matches = "1")
class VSphereSmokeTest {
    @Test fun `list and get agree against live vcsim`() {
        val adapter = VSphereAdapter()
        val listResult = adapter.listVirtualMachines()
        val listed = assertIs<Ok<List<dev.iaassim.application.ObservedVirtualMachine>>>(
            listResult,
            "actual result: $listResult",
        )
        assertTrue(listed.value.isNotEmpty())
        val first = listed.value.first()
        val getResult = adapter.getVirtualMachine(first.backendRef)
        val fetched = assertIs<Ok<dev.iaassim.application.ObservedVirtualMachine>>(
            getResult,
            "actual result: $getResult",
        ).value
        assertEquals(first.backendRef, fetched.backendRef)
        assertEquals(first.name, fetched.name)
        assertEquals(first.powerState, fetched.powerState)
    }

    @Test fun `submits polls and restores power state against live vcsim`() {
        val adapter = VSphereAdapter()
        val first = assertIs<Ok<List<dev.iaassim.application.ObservedVirtualMachine>>>(adapter.listVirtualMachines()).value.first()
        val firstCommand = if (first.powerState == PowerState.STOPPED) PowerCommand.START else PowerCommand.STOP
        val secondCommand = if (firstCommand == PowerCommand.START) PowerCommand.STOP else PowerCommand.START
        submitAndAwait(adapter, first.backendRef, firstCommand)
        assertEquals(if (firstCommand == PowerCommand.START) PowerState.RUNNING else PowerState.STOPPED,
            assertIs<Ok<dev.iaassim.application.ObservedVirtualMachine>>(adapter.getVirtualMachine(first.backendRef)).value.powerState)
        submitAndAwait(adapter, first.backendRef, secondCommand)
        assertEquals(first.powerState,
            assertIs<Ok<dev.iaassim.application.ObservedVirtualMachine>>(adapter.getVirtualMachine(first.backendRef)).value.powerState)
    }

    @Test fun `creates blank VM and durably finalizes its future identity`() {
        val adapter = VSphereAdapter(); val path = kotlin.io.path.createTempDirectory().resolve("create.db")
        val identity = SQLiteVirtualMachineIdentityAdapter(path); val store = SQLiteOperationStore(path)
        val futureId = VirtualMachineId(UuidCreator.getTimeOrderedEpoch())
        val operation = Operation(OperationId(UuidCreator.getTimeOrderedEpoch()),
            ResourceReference("virtualMachines", futureId.value.toString()), "CREATE", Running)
        val name = "iaas-sim-${futureId.value.toString().takeLast(8)}"
        val task = assertIs<Ok<BackendOperationRef>>(adapter.submitCreateVirtualMachine(futureId,
            VirtualMachineCreateSpec(name, 1, 1024))).value
        assertIs<Ok<Operation>>(store.createRunning(operation, task))
        assertIs<dev.iaassim.result.Err<VirtualMachineIdentityNotFound>>(identity.getBackendRef(futureId))
        assertTrue(assertIs<Ok<List<dev.iaassim.domain.entity.virtualmachine.VirtualMachine>>>(
            listVirtualMachines(adapter, identity)).value.none { it.id == futureId })
        var completed: Operation? = null
        repeat(100) {
            when (val result = getOperation(store, adapter, operation.id, SQLiteVirtualMachineCreateFinalizer(path))) {
                is Ok -> if (result.value.status == Succeeded) { completed = result.value; return@repeat }
                is dev.iaassim.result.Err -> fail("create polling failed: $result")
            }
            Thread.sleep(100)
        }
        assertEquals(Succeeded, completed?.status)
        val backendRef = assertIs<Ok<BackendVirtualMachineRef>>(SQLiteVirtualMachineIdentityAdapter(path).getBackendRef(futureId)).value
        val created = assertIs<Ok<ObservedVirtualMachine>>(adapter.getVirtualMachine(backendRef)).value
        assertEquals(name, created.name); assertEquals(PowerState.STOPPED, created.powerState)
        assertEquals(futureId, created.creationVirtualMachineId)
    }

    private fun submitAndAwait(adapter: VSphereAdapter, ref: dev.iaassim.application.BackendVirtualMachineRef,
        command: PowerCommand) {
        val task = assertIs<Ok<dev.iaassim.application.BackendOperationRef>>(adapter.submitPowerCommand(ref, command)).value
        repeat(50) {
            when (val status = assertIs<Ok<dev.iaassim.application.BackendOperationStatus>>(adapter.getOperationStatus(task)).value) {
                is BackendOperationSucceeded -> return
                BackendOperationRunning -> Thread.sleep(100)
                else -> fail("task failed: $status")
            }
        }
        fail("task did not complete")
    }
}
