package dev.iaassim.domain.entity.virtualmachine

import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome

fun validatePowerCommand(
    vm: VirtualMachine,
    command: PowerCommand,
): Outcome<AcceptedPowerCommand, PowerCommandError> =
    when (vm.powerState) {
        PowerState.STOPPED ->
            when (command) {
                PowerCommand.START -> Ok(AcceptedPowerCommand(vm.id, command))
                PowerCommand.STOP -> Err(AlreadyStopped(vm.id))
            }
        PowerState.RUNNING ->
            when (command) {
                PowerCommand.START -> Err(AlreadyRunning(vm.id))
                PowerCommand.STOP -> Ok(AcceptedPowerCommand(vm.id, command))
            }
    }
