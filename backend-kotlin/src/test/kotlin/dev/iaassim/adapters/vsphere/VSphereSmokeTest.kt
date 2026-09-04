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
        val listed = assertIs<Ok<List<dev.iaassim.application.ObservedVirtualMachine>>>(adapter.listVirtualMachines())
        assertTrue(listed.value.isNotEmpty())
        val first = listed.value.first()
        val fetched = assertIs<Ok<dev.iaassim.application.ObservedVirtualMachine>>(adapter.getVirtualMachine(first.backendRef)).value
        assertEquals(first.backendRef, fetched.backendRef)
        assertEquals(first.name, fetched.name)
        assertEquals(first.powerState, fetched.powerState)
    }
}
