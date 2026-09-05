package dev.iaassim.domain.entity.operation

import dev.iaassim.domain.ResourceReference
import java.util.UUID

@JvmInline value class OperationId(val value: UUID)
data class OperationFailure(val reason: String)
sealed interface OperationStatus
data object Running : OperationStatus
data object Succeeded : OperationStatus
data class Failed(val failure: OperationFailure) : OperationStatus
data class Operation(val id: OperationId, val target: ResourceReference, val action: String, val status: OperationStatus)

fun isTerminal(status: OperationStatus): Boolean = when (status) {
    Running -> false
    Succeeded, is Failed -> true
}
