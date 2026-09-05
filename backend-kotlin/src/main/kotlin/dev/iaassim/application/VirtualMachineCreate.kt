package dev.iaassim.application

import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.instancetype.InstanceTypeId
import dev.iaassim.domain.entity.operation.*
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.*

data class VirtualMachineCreateSpec(val name: String, val vcpus: Int, val memoryMiB: Int)
data class InvalidVirtualMachineCreateSpec(val reason: String)
data class VirtualMachineCreateBackendSubmissionFailure(val reason: String)
fun validateVirtualMachineCreateSpec(spec: VirtualMachineCreateSpec): Outcome<VirtualMachineCreateSpec, InvalidVirtualMachineCreateSpec> =
    if (spec.name == "" || spec.vcpus <= 0 || spec.memoryMiB <= 0) Err(InvalidVirtualMachineCreateSpec("invalid create spec")) else Ok(spec)

sealed interface VirtualMachineCreateError
data class VirtualMachineCreateInstanceTypeNotFound(val failure: InstanceTypeNotFound) : VirtualMachineCreateError
data class VirtualMachineCreateInstanceTypePersistenceFailure(val failure: InstanceTypePersistenceFailure) : VirtualMachineCreateError
data class VirtualMachineCreateInvalidSpec(val failure: InvalidVirtualMachineCreateSpec) : VirtualMachineCreateError
data class VirtualMachineCreateSubmissionFailure(val failure: VirtualMachineCreateBackendSubmissionFailure) : VirtualMachineCreateError
data class VirtualMachineCreateOperationPersistenceFailure(val failure: OperationPersistenceFailure) : VirtualMachineCreateError

fun createVirtualMachine(port: VirtualMachinePort, instanceTypes: InstanceTypeStorePort, operations: OperationStorePort,
    virtualMachineId: VirtualMachineId, operationId: OperationId, name: String, instanceTypeId: InstanceTypeId):
    Outcome<Operation, VirtualMachineCreateError> {
    val instanceType = when (val result = instanceTypes.getInstanceType(instanceTypeId)) {
        is Ok -> result.value
        is Err -> return when (val error = result.error) {
            is InstanceTypeNotFound -> Err(VirtualMachineCreateInstanceTypeNotFound(error))
            is InstanceTypePersistenceFailure -> Err(VirtualMachineCreateInstanceTypePersistenceFailure(error))
        }
    }
    val spec = when (val result = validateVirtualMachineCreateSpec(VirtualMachineCreateSpec(name, instanceType.vcpus, instanceType.memoryMiB))) {
        is Ok -> result.value
        is Err -> return Err(VirtualMachineCreateInvalidSpec(result.error))
    }
    val backendRef = when (val result = port.submitCreateVirtualMachine(virtualMachineId, spec)) {
        is Ok -> result.value
        is Err -> return Err(VirtualMachineCreateSubmissionFailure(result.error))
    }
    val operation = Operation(operationId, ResourceReference("virtualMachines", virtualMachineId.value.toString()), "CREATE", Running)
    return when (val result = operations.createRunning(operation, backendRef)) {
        is Ok -> result
        is Err -> Err(VirtualMachineCreateOperationPersistenceFailure(result.error))
    }
}
