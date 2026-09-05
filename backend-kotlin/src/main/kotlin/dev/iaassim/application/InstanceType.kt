package dev.iaassim.application

import dev.iaassim.domain.entity.instancetype.*
import dev.iaassim.result.Outcome

sealed interface InstanceTypeStoreError
data class InstanceTypeNotFound(val instanceTypeId: InstanceTypeId) : InstanceTypeStoreError
data class InstanceTypePersistenceFailure(val operation: String, val reason: String) : InstanceTypeStoreError
interface InstanceTypeStorePort {
    fun listInstanceTypes(): Outcome<List<InstanceType>, InstanceTypePersistenceFailure>
    fun getInstanceType(instanceTypeId: InstanceTypeId): Outcome<InstanceType, InstanceTypeStoreError>
}
fun listInstanceTypes(store: InstanceTypeStorePort) = store.listInstanceTypes()
fun getInstanceType(store: InstanceTypeStorePort, id: InstanceTypeId) = store.getInstanceType(id)
