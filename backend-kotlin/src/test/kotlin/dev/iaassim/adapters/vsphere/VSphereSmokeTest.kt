package dev.iaassim.adapters.vsphere

import dev.iaassim.result.Ok
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable

@EnabledIfEnvironmentVariable(named = "VSPHERE_SMOKE", matches = "1")
class VSphereSmokeTest {
    @Test fun `list and get agree against live vcsim`() {
        val adapter = VSphereAdapter()
        val listResult = adapter.listVirtualMachines()
        val listed = assertIs<Ok<List<dev.iaassim.application.ObservedVirtualMachine>>>(
            listResult,
            "actual result: $listResult",
        )
        assertTrue(listed.value.isNotEmpty())
        val first = listed.value.first()
        val getResult = adapter.getVirtualMachine(first.backendRef)
        val fetched = assertIs<Ok<dev.iaassim.application.ObservedVirtualMachine>>(
            getResult,
            "actual result: $getResult",
        ).value
        assertEquals(first.backendRef, fetched.backendRef)
        assertEquals(first.name, fetched.name)
        assertEquals(first.powerState, fetched.powerState)
    }
}
