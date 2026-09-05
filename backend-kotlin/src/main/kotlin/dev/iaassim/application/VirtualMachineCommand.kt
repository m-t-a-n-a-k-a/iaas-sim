package dev.iaassim.application

import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.operation.Operation
import dev.iaassim.domain.entity.operation.OperationId
import dev.iaassim.domain.entity.operation.Running
import dev.iaassim.domain.entity.virtualmachine.AcceptedPowerCommand
import dev.iaassim.domain.entity.virtualmachine.AlreadyRunning
import dev.iaassim.domain.entity.virtualmachine.AlreadyStopped
import dev.iaassim.domain.entity.virtualmachine.PowerCommand
import dev.iaassim.domain.entity.virtualmachine.VirtualMachine
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.domain.entity.virtualmachine.validatePowerCommand
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome

sealed interface PowerCommandExecutionError
data class PowerCommandVirtualMachineNotFound(val virtualMachineId: VirtualMachineId) : PowerCommandExecutionError
data class PowerCommandObservationFailure(val virtualMachineId: VirtualMachineId, val reason: String) : PowerCommandExecutionError
data class PowerCommandIdentityFailure(val virtualMachineId: VirtualMachineId, val reason: String) : PowerCommandExecutionError
data class PowerCommandSubmissionFailure(val virtualMachineId: VirtualMachineId, val reason: String) : PowerCommandExecutionError
data class PowerCommandConflict(val virtualMachineId: VirtualMachineId, val command: PowerCommand) : PowerCommandExecutionError
data class PowerCommandOperationPersistenceFailure(val failure: OperationPersistenceFailure) : PowerCommandExecutionError

fun executePowerCommand(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    virtualMachineId: VirtualMachineId,
    operationId: OperationId,
    command: PowerCommand,
): Outcome<Operation, PowerCommandExecutionError> {
    val backendRef = when (val result = identity.getBackendRef(virtualMachineId)) {
        is Ok -> result.value
        is Err -> return when (val error = result.error) {
            is VirtualMachineIdentityNotFound -> Err(PowerCommandVirtualMachineNotFound(virtualMachineId))
            is VirtualMachineIdentityPersistenceFailure -> Err(PowerCommandIdentityFailure(virtualMachineId, error.reason))
        }
    }
    val observation = when (val result = port.getVirtualMachine(backendRef)) {
        is Ok -> result.value
        is Err -> return when (val error = result.error) {
            is VirtualMachineBackendNotFound -> Err(PowerCommandVirtualMachineNotFound(virtualMachineId))
            is VirtualMachineBackendFailure -> Err(PowerCommandObservationFailure(virtualMachineId, error.reason))
        }
    }
    if (observation.creationVirtualMachineId != null && observation.creationVirtualMachineId != virtualMachineId) {
        return Err(PowerCommandIdentityFailure(virtualMachineId, "creation marker does not match requested identity"))
    }
    val accepted: AcceptedPowerCommand = when (val result = validatePowerCommand(
        VirtualMachine(virtualMachineId, observation.name, observation.powerState), command,
    )) {
        is Ok -> result.value
        is Err -> return when (result.error) {
            is AlreadyRunning, is AlreadyStopped -> Err(PowerCommandConflict(virtualMachineId, command))
        }
    }
    val taskRef = when (val result = port.submitPowerCommand(backendRef, accepted.command)) {
        is Ok -> result.value
        is Err -> return Err(PowerCommandSubmissionFailure(virtualMachineId, result.error.reason))
    }
    val operation = Operation(
        operationId,
        ResourceReference("virtualMachines", accepted.virtualMachineId.value.toString()),
        accepted.command.name,
        Running,
    )
    return when (val result = store.createRunning(operation, taskRef)) {
        is Ok -> result
        is Err -> Err(PowerCommandOperationPersistenceFailure(result.error))
    }
}

fun startVirtualMachine(port: VirtualMachinePort, identity: VirtualMachineIdentityPort, store: OperationStorePort,
    virtualMachineId: VirtualMachineId, operationId: OperationId) =
    executePowerCommand(port, identity, store, virtualMachineId, operationId, PowerCommand.START)

fun stopVirtualMachine(port: VirtualMachinePort, identity: VirtualMachineIdentityPort, store: OperationStorePort,
    virtualMachineId: VirtualMachineId, operationId: OperationId) =
    executePowerCommand(port, identity, store, virtualMachineId, operationId, PowerCommand.STOP)
