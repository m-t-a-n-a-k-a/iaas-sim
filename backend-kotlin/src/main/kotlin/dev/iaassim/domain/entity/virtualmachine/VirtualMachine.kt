package dev.iaassim.domain.entity.virtualmachine

import java.util.UUID

@JvmInline
value class VirtualMachineId(val value: UUID)

enum class PowerState {
    STOPPED,
    RUNNING,
}

enum class PowerCommand {
    START,
    STOP,
}

data class VirtualMachine(
    val id: VirtualMachineId,
    val name: String,
    /** The power state observed from the backend, not a desired state. */
    val powerState: PowerState,
)

data class AcceptedPowerCommand(
    val virtualMachineId: VirtualMachineId,
    val command: PowerCommand,
)

sealed interface PowerCommandError

data class AlreadyRunning(
    val virtualMachineId: VirtualMachineId,
) : PowerCommandError

data class AlreadyStopped(
    val virtualMachineId: VirtualMachineId,
) : PowerCommandError
