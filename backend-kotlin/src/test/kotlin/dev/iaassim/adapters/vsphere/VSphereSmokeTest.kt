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

    private fun submitAndAwait(adapter: VSphereAdapter, ref: dev.iaassim.application.BackendVirtualMachineRef,
        command: PowerCommand) {
        val task = assertIs<Ok<dev.iaassim.application.BackendOperationRef>>(adapter.submitPowerCommand(ref, command)).value
        repeat(50) {
            when (val status = assertIs<Ok<dev.iaassim.application.BackendOperationStatus>>(adapter.getOperationStatus(task)).value) {
                BackendOperationSucceeded -> return
                BackendOperationRunning -> Thread.sleep(100)
                else -> fail("task failed: $status")
            }
        }
        fail("task did not complete")
    }
}
