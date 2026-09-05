package dev.iaassim.application

import dev.iaassim.domain.entity.virtualmachine.PowerState
import dev.iaassim.domain.entity.virtualmachine.PowerCommand
import dev.iaassim.domain.entity.virtualmachine.VirtualMachine
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome

@JvmInline
value class BackendVirtualMachineRef(val value: String)

data class ObservedVirtualMachine(
    val backendRef: BackendVirtualMachineRef,
    val name: String,
    val powerState: PowerState,
    val creationVirtualMachineId: VirtualMachineId? = null,
)

sealed interface VirtualMachineBackendError
data class VirtualMachineBackendNotFound(val backendRef: BackendVirtualMachineRef) : VirtualMachineBackendError
data class VirtualMachineBackendFailure(val operation: String, val reason: String) : VirtualMachineBackendError,
    VirtualMachineReadError

interface VirtualMachinePort {
    fun listVirtualMachines(): Outcome<List<ObservedVirtualMachine>, VirtualMachineBackendFailure>
    fun getVirtualMachine(backendRef: BackendVirtualMachineRef): Outcome<ObservedVirtualMachine, VirtualMachineBackendError>
    fun submitPowerCommand(
        backendRef: BackendVirtualMachineRef,
        command: PowerCommand,
    ): Outcome<BackendOperationRef, PowerCommandBackendSubmissionFailure>
}

data class PowerCommandBackendSubmissionFailure(val backendRef: BackendVirtualMachineRef, val reason: String)

data class VirtualMachineIdentityNotFound(val virtualMachineId: VirtualMachineId) : VirtualMachineIdentityError
data class VirtualMachineIdentityPersistenceFailure(val operation: String, val reason: String) :
    VirtualMachineIdentityError, VirtualMachineReadError
sealed interface VirtualMachineIdentityError

interface VirtualMachineIdentityPort {
    fun findByBackendRef(backendRef: BackendVirtualMachineRef):
        Outcome<VirtualMachineId?, VirtualMachineIdentityPersistenceFailure>
    fun getOrCreateByBackendRef(backendRef: BackendVirtualMachineRef):
        Outcome<VirtualMachineId, VirtualMachineIdentityPersistenceFailure>
    fun getBackendRef(virtualMachineId: VirtualMachineId):
        Outcome<BackendVirtualMachineRef, VirtualMachineIdentityError>
}

sealed interface VirtualMachineReadError
data class VirtualMachineNotFound(val virtualMachineId: VirtualMachineId) : VirtualMachineReadError

fun listVirtualMachines(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
): Outcome<List<VirtualMachine>, VirtualMachineReadError> {
    val observations = when (val result = port.listVirtualMachines()) {
        is Ok -> result.value
        is Err -> return Err(result.error)
    }
    val projected = mutableListOf<VirtualMachine>()
    for (observation in observations) {
        val publicId = if (observation.creationVirtualMachineId == null) {
            when (val result = identity.getOrCreateByBackendRef(observation.backendRef)) {
                is Ok -> result.value
                is Err -> return Err(result.error)
            }
        } else {
            when (val result = identity.findByBackendRef(observation.backendRef)) {
                is Err -> return Err(result.error)
                is Ok -> result.value ?: continue
            }
        }
        if (observation.creationVirtualMachineId != null && observation.creationVirtualMachineId != publicId) {
            return Err(VirtualMachineIdentityPersistenceFailure("list", "creation marker does not match identity mapping"))
        }
        projected.add(VirtualMachine(publicId, observation.name, observation.powerState))
    }
    return Ok(projected.toList())
}

fun getVirtualMachine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    virtualMachineId: VirtualMachineId,
): Outcome<VirtualMachine, VirtualMachineReadError> {
    val backendRef = when (val result = identity.getBackendRef(virtualMachineId)) {
        is Ok -> result.value
        is Err -> return when (result.error) {
            is VirtualMachineIdentityNotFound -> Err(VirtualMachineNotFound(virtualMachineId))
            is VirtualMachineIdentityPersistenceFailure -> Err(result.error)
        }
    }
    val observation = when (val result = port.getVirtualMachine(backendRef)) {
        is Ok -> result.value
        is Err -> return when (val error = result.error) {
            is VirtualMachineBackendNotFound -> Err(VirtualMachineNotFound(virtualMachineId))
            is VirtualMachineBackendFailure -> Err(error)
        }
    }
    if (observation.creationVirtualMachineId != null && observation.creationVirtualMachineId != virtualMachineId) {
        return Err(VirtualMachineIdentityPersistenceFailure("get", "creation marker does not match requested identity"))
    }
    return Ok(VirtualMachine(virtualMachineId, observation.name, observation.powerState))
}
