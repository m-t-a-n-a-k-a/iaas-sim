package dev.iaassim.adapters.identity

import com.github.f4b6a3.uuid.UuidCreator
import dev.iaassim.application.BackendVirtualMachineRef
import dev.iaassim.application.VirtualMachineIdentityError
import dev.iaassim.application.VirtualMachineIdentityNotFound
import dev.iaassim.application.VirtualMachineIdentityPersistenceFailure
import dev.iaassim.application.VirtualMachineIdentityPort
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome

class InMemoryVirtualMachineIdentityAdapter : VirtualMachineIdentityPort {
    private val backendToPublic = mutableMapOf<BackendVirtualMachineRef, VirtualMachineId>()
    private val publicToBackend = mutableMapOf<VirtualMachineId, BackendVirtualMachineRef>()

    @Synchronized
    override fun findByBackendRef(backendRef: BackendVirtualMachineRef):
        Outcome<VirtualMachineId?, VirtualMachineIdentityPersistenceFailure> = Ok(backendToPublic[backendRef])

    @Synchronized
    override fun getOrCreateByBackendRef(backendRef: BackendVirtualMachineRef):
        Outcome<VirtualMachineId, VirtualMachineIdentityPersistenceFailure> {
        val id = backendToPublic[backendRef] ?: VirtualMachineId(UuidCreator.getTimeOrderedEpoch())
        backendToPublic[backendRef] = id
        publicToBackend[id] = backendRef
        return Ok(id)
    }

    @Synchronized
    override fun getBackendRef(virtualMachineId: VirtualMachineId):
        Outcome<BackendVirtualMachineRef, VirtualMachineIdentityError> =
        publicToBackend[virtualMachineId]?.let(::Ok) ?: Err(VirtualMachineIdentityNotFound(virtualMachineId))
}
