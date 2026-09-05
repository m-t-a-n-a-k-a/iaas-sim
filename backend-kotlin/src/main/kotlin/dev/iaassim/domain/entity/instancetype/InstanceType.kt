package dev.iaassim.domain.entity.instancetype

import java.util.UUID

@JvmInline value class InstanceTypeId(val value: UUID)
data class InstanceType(val id: InstanceTypeId, val name: String, val vcpus: Int, val memoryMiB: Int)
