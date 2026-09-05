package dev.iaassim.domain.entity.operation

import dev.iaassim.domain.ResourceReference
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals

class OperationTest {
    @Test fun `terminal decision table and UUID backed identity`() {
        val cases = listOf(Running to false, Succeeded to true, Failed(OperationFailure("failed")) to true)
        cases.forEach { (status, expected) -> assertEquals(expected, isTerminal(status)) }
        val uuid = UUID.fromString("0198f5d0-7300-7000-8000-000000000000")
        val operation = Operation(OperationId(uuid), ResourceReference("virtualMachines", "vm"), "START", Running)
        assertEquals(uuid, operation.id.value)
    }
}
