package dev.iaassim.application

import dev.iaassim.domain.entity.operation.*
import dev.iaassim.domain.entity.virtualmachine.*
import dev.iaassim.result.*
import java.util.UUID
import kotlin.test.*

private val commandVmId = VirtualMachineId(UUID.fromString("0198f5d0-7300-7000-8000-000000000010"))
private val commandOperationId = OperationId(UUID.fromString("0198f5d0-7300-7000-8000-000000000011"))
private val commandRef = BackendVirtualMachineRef("vm-1")
private class CommandIdentity(var result: Outcome<BackendVirtualMachineRef, VirtualMachineIdentityError> = Ok(commandRef)) : VirtualMachineIdentityPort {
    override fun findByBackendRef(backendRef: BackendVirtualMachineRef) = Ok<VirtualMachineId?>(null)
    override fun getOrCreateByBackendRef(backendRef: BackendVirtualMachineRef) = Ok(commandVmId)
    override fun getBackendRef(virtualMachineId: VirtualMachineId) = result
}
private class CommandPort(var state: PowerState, var marker: VirtualMachineId? = null,
    var observationFailure: Boolean = false, var submissionFailure: Boolean = false) : VirtualMachinePort {
    var observations = 0; var submissions = 0; var submitted: PowerCommand? = null
    override fun listVirtualMachines() = Ok(emptyList<ObservedVirtualMachine>())
    override fun getVirtualMachine(backendRef: BackendVirtualMachineRef): Outcome<ObservedVirtualMachine, VirtualMachineBackendError> {
        observations++; return if (observationFailure) Err(VirtualMachineBackendFailure("get", "secret"))
        else Ok(ObservedVirtualMachine(commandRef, "vm", state, marker))
    }
    override fun submitPowerCommand(backendRef: BackendVirtualMachineRef, command: PowerCommand): Outcome<BackendOperationRef, PowerCommandBackendSubmissionFailure> {
        submissions++; submitted = command
        return if (submissionFailure) Err(PowerCommandBackendSubmissionFailure(backendRef, "secret")) else Ok(BackendOperationRef("task"))
    }
}
private class CommandStore(var failure: Boolean = false) : OperationStorePort {
    var creates = 0
    override fun createRunning(operation: Operation, backendRef: BackendOperationRef): Outcome<Operation, OperationPersistenceFailure> {
        creates++; return if (failure) Err(OperationPersistenceFailure("create", "down")) else Ok(operation)
    }
    override fun get(operationId: OperationId): Outcome<StoredOperation, OperationStoreError> = Err(OperationNotFound(operationId))
    override fun complete(operation: Operation): Outcome<Operation, OperationStoreError> = Ok(operation)
}
class VirtualMachineCommandTest {
    @Test fun `valid decision table submits validated command and persists running operation`() {
        listOf(PowerState.STOPPED to PowerCommand.START, PowerState.RUNNING to PowerCommand.STOP).forEach { (state, command) ->
            val port = CommandPort(state); val store = CommandStore()
            val result = assertIs<Ok<Operation>>(executePowerCommand(port, CommandIdentity(), store, commandVmId,
                commandOperationId, command)).value
            assertEquals(command, port.submitted); assertEquals(Running, result.status); assertEquals(command.name, result.action)
            assertEquals(1, store.creates)
        }
    }
    @Test fun `conflicts have no submission or persistence`() {
        listOf(PowerState.RUNNING to PowerCommand.START, PowerState.STOPPED to PowerCommand.STOP).forEach { (state, command) ->
            val port = CommandPort(state); val store = CommandStore()
            assertIs<Err<PowerCommandConflict>>(executePowerCommand(port, CommandIdentity(), store, commandVmId,
                commandOperationId, command)); assertEquals(0, port.submissions); assertEquals(0, store.creates)
        }
    }
    @Test fun `all pre-submission failures prevent later effects and typed failures propagate`() {
        val missingPort = CommandPort(PowerState.STOPPED); val missingStore = CommandStore()
        assertIs<Err<PowerCommandVirtualMachineNotFound>>(executePowerCommand(missingPort,
            CommandIdentity(Err(VirtualMachineIdentityNotFound(commandVmId))), missingStore, commandVmId, commandOperationId, PowerCommand.START))
        assertEquals(0, missingPort.observations)
        listOf(CommandPort(PowerState.STOPPED, observationFailure = true), CommandPort(PowerState.STOPPED,
            marker = VirtualMachineId(UUID.fromString("0198f5d0-7300-7000-8000-000000000012")))).forEach { port ->
            val store = CommandStore(); assertIs<Err<PowerCommandExecutionError>>(executePowerCommand(port, CommandIdentity(), store,
                commandVmId, commandOperationId, PowerCommand.START)); assertEquals(0, port.submissions); assertEquals(0, store.creates)
        }
        val submit = CommandPort(PowerState.STOPPED, submissionFailure = true); val store = CommandStore()
        assertIs<Err<PowerCommandSubmissionFailure>>(executePowerCommand(submit, CommandIdentity(), store, commandVmId,
            commandOperationId, PowerCommand.START)); assertEquals(0, store.creates)
        assertIs<Err<PowerCommandOperationPersistenceFailure>>(executePowerCommand(CommandPort(PowerState.STOPPED),
            CommandIdentity(), CommandStore(true), commandVmId, commandOperationId, PowerCommand.START))
    }
}
