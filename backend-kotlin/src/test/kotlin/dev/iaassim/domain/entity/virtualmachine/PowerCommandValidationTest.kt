package dev.iaassim.domain.entity.virtualmachine

import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals

class PowerCommandValidationTest {
    private val virtualMachineId =
        VirtualMachineId(UUID.fromString("0198f5d0-7300-7000-8000-000000000000"))

    @Test
    fun `validates the complete power state and command decision table`() {
        val cases =
            listOf(
                Case(
                    state = PowerState.STOPPED,
                    command = PowerCommand.START,
                    expected = Ok(AcceptedPowerCommand(virtualMachineId, PowerCommand.START)),
                ),
                Case(
                    state = PowerState.STOPPED,
                    command = PowerCommand.STOP,
                    expected = Err(AlreadyStopped(virtualMachineId)),
                ),
                Case(
                    state = PowerState.RUNNING,
                    command = PowerCommand.START,
                    expected = Err(AlreadyRunning(virtualMachineId)),
                ),
                Case(
                    state = PowerState.RUNNING,
                    command = PowerCommand.STOP,
                    expected = Ok(AcceptedPowerCommand(virtualMachineId, PowerCommand.STOP)),
                ),
            )

        cases.forEach { case ->
            val vm = VirtualMachine(virtualMachineId, "vm-1", case.state)

            assertEquals(case.expected, validatePowerCommand(vm, case.command))
        }
    }

    private data class Case(
        val state: PowerState,
        val command: PowerCommand,
        val expected: Outcome<AcceptedPowerCommand, PowerCommandError>,
    )
}
