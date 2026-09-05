package dev.iaassim

import dev.iaassim.adapters.identity.InMemoryVirtualMachineIdentityAdapter
import dev.iaassim.application.BackendVirtualMachineRef
import dev.iaassim.application.ObservedVirtualMachine
import dev.iaassim.application.VirtualMachineBackendError
import dev.iaassim.application.VirtualMachineBackendFailure
import dev.iaassim.application.VirtualMachineBackendNotFound
import dev.iaassim.application.VirtualMachinePort
import dev.iaassim.domain.entity.virtualmachine.PowerState
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private class HttpFakePort(
    var failure: Boolean = false,
) : VirtualMachinePort {
    val observed = ObservedVirtualMachine(BackendVirtualMachineRef("vm-1"), "vcsim-vm", PowerState.RUNNING)
    override fun listVirtualMachines(): Outcome<List<ObservedVirtualMachine>, VirtualMachineBackendFailure> =
        if (failure) Err(VirtualMachineBackendFailure("list", "secret")) else Ok(listOf(observed))
    override fun getVirtualMachine(backendRef: BackendVirtualMachineRef): Outcome<ObservedVirtualMachine, VirtualMachineBackendError> =
        if (failure) Err(VirtualMachineBackendFailure("get", "secret"))
        else if (backendRef == observed.backendRef) Ok(observed) else Err(VirtualMachineBackendNotFound(backendRef))
}

class ApplicationTest {
    @Test
    fun `health reports skeleton liveness`() = testApplication {
        application { module() }

        val response = client.get("/health")

        assertEquals(HttpStatusCode.OK, response.status)
        assertEquals("{\"status\":\"ok\"}", response.bodyAsText())
    }

    @Test fun `list and get return HTTP DTO JSON`() = testApplication {
        val port = HttpFakePort()
        val identity = InMemoryVirtualMachineIdentityAdapter()
        application { module(VirtualMachineDependencies(port, identity)) }
        val list = client.get("/v1/virtualMachines")
        assertEquals(HttpStatusCode.OK, list.status)
        assertTrue(list.bodyAsText().contains("\"powerState\":\"RUNNING\""))
        val id = requireNotNull(Regex("[0-9a-f-]{36}").find(list.bodyAsText())).value
        val get = client.get("/v1/virtualMachines/$id")
        assertEquals(HttpStatusCode.OK, get.status)
        assertTrue(get.bodyAsText().contains("vcsim-vm"))
    }

    @Test fun `invalid identifiers return 422 and missing returns 404`() = testApplication {
        val port = HttpFakePort()
        val identity = InMemoryVirtualMachineIdentityAdapter()
        application { module(VirtualMachineDependencies(port, identity)) }
        assertEquals(HttpStatusCode.UnprocessableEntity, client.get("/v1/virtualMachines/nope").status)
        assertEquals(HttpStatusCode.UnprocessableEntity, client.get("/v1/virtualMachines/00000000-0000-4000-8000-000000000000").status)
        assertEquals(HttpStatusCode.NotFound, client.get("/v1/virtualMachines/01890f4c-7f15-7cc2-98c8-0800200c9a66").status)
    }

    @Test fun `backend failure is sanitized as 502`() = testApplication {
        application { module(VirtualMachineDependencies(HttpFakePort(true), InMemoryVirtualMachineIdentityAdapter())) }
        val response = client.get("/v1/virtualMachines")
        assertEquals(HttpStatusCode.BadGateway, response.status)
        assertEquals("{\"detail\":\"VirtualMachine backend request failed\"}", response.bodyAsText())
    }
}
