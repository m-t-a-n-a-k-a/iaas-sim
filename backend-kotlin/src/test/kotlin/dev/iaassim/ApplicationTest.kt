package dev.iaassim

import dev.iaassim.adapters.identity.InMemoryVirtualMachineIdentityAdapter
import dev.iaassim.adapters.sqlite.SQLiteOperationStore
import dev.iaassim.application.BackendOperationPort
import dev.iaassim.application.BackendOperationRunning
import dev.iaassim.application.BackendOperationStatus
import dev.iaassim.application.OperationPollingFailure
import dev.iaassim.application.BackendVirtualMachineRef
import dev.iaassim.application.BackendOperationRef
import dev.iaassim.application.PowerCommandBackendSubmissionFailure
import dev.iaassim.application.ObservedVirtualMachine
import dev.iaassim.application.VirtualMachineBackendError
import dev.iaassim.application.VirtualMachineBackendFailure
import dev.iaassim.application.VirtualMachineBackendNotFound
import dev.iaassim.application.VirtualMachinePort
import dev.iaassim.domain.entity.virtualmachine.PowerState
import dev.iaassim.domain.entity.virtualmachine.PowerCommand
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpStatusCode
import io.ktor.server.testing.testApplication
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

private class HttpFakePort(
    var failure: Boolean = false,
) : VirtualMachinePort, BackendOperationPort {
    val observed = ObservedVirtualMachine(BackendVirtualMachineRef("vm-1"), "vcsim-vm", PowerState.RUNNING)
    override fun listVirtualMachines(): Outcome<List<ObservedVirtualMachine>, VirtualMachineBackendFailure> =
        if (failure) Err(VirtualMachineBackendFailure("list", "secret")) else Ok(listOf(observed))
    override fun getVirtualMachine(backendRef: BackendVirtualMachineRef): Outcome<ObservedVirtualMachine, VirtualMachineBackendError> =
        if (failure) Err(VirtualMachineBackendFailure("get", "secret"))
        else if (backendRef == observed.backendRef) Ok(observed) else Err(VirtualMachineBackendNotFound(backendRef))
    override fun submitPowerCommand(backendRef: BackendVirtualMachineRef, command: PowerCommand):
        Outcome<BackendOperationRef, PowerCommandBackendSubmissionFailure> = Ok(BackendOperationRef("task-1"))
    override fun getOperationStatus(backendRef: BackendOperationRef): Outcome<BackendOperationStatus, OperationPollingFailure> =
        Ok(BackendOperationRunning)
}

private fun dependencies(port: HttpFakePort) = VirtualMachineDependencies(
    port, InMemoryVirtualMachineIdentityAdapter(), SQLiteOperationStore(kotlin.io.path.createTempFile(suffix = ".db")), port,
)

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
        application { module(VirtualMachineDependencies(port, identity, SQLiteOperationStore(kotlin.io.path.createTempFile(suffix = ".db")), port)) }
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
        application { module(VirtualMachineDependencies(port, identity, SQLiteOperationStore(kotlin.io.path.createTempFile(suffix = ".db")), port)) }
        assertEquals(HttpStatusCode.UnprocessableEntity, client.get("/v1/virtualMachines/nope").status)
        assertEquals(HttpStatusCode.UnprocessableEntity, client.get("/v1/virtualMachines/00000000-0000-4000-8000-000000000000").status)
        assertEquals(HttpStatusCode.NotFound, client.get("/v1/virtualMachines/01890f4c-7f15-7cc2-98c8-0800200c9a66").status)
    }

    @Test fun `backend failure is sanitized as 502`() = testApplication {
        application { module(dependencies(HttpFakePort(true))) }
        val response = client.get("/v1/virtualMachines")
        assertEquals(HttpStatusCode.BadGateway, response.status)
        assertEquals("{\"detail\":\"VirtualMachine backend request failed\"}", response.bodyAsText())
    }

    @Test fun `stop accepts persistent running operation and get polls without leaking backend ref`() = testApplication {
        val port = HttpFakePort(); val identity = InMemoryVirtualMachineIdentityAdapter()
        application { module(VirtualMachineDependencies(port, identity,
            SQLiteOperationStore(kotlin.io.path.createTempFile(suffix = ".db")), port)) }
        val list = client.get("/v1/virtualMachines").bodyAsText()
        val vmId = requireNotNull(Regex("[0-9a-f-]{36}").find(list)).value
        val accepted = client.post("/v1/virtualMachines/$vmId:stop")
        assertEquals(HttpStatusCode.Accepted, accepted.status)
        assertTrue(requireNotNull(accepted.headers["Location"]).startsWith("/v1/operations/"))
        val body = accepted.bodyAsText()
        assertTrue(body.contains("\"action\":\"STOP\"")); assertTrue(body.contains("\"state\":\"RUNNING\""))
        assertTrue(!body.contains("task-1"))
        val fetched = client.get(requireNotNull(accepted.headers["Location"]))
        assertEquals(HttpStatusCode.OK, fetched.status); assertTrue(!fetched.bodyAsText().contains("task-1"))
    }

    @Test fun `command and operation invalid identifiers return 422 and conflict returns 409`() = testApplication {
        val port = HttpFakePort(); val identity = InMemoryVirtualMachineIdentityAdapter()
        application { module(VirtualMachineDependencies(port, identity,
            SQLiteOperationStore(kotlin.io.path.createTempFile(suffix = ".db")), port)) }
        assertEquals(HttpStatusCode.UnprocessableEntity, client.post("/v1/virtualMachines/nope:start").status)
        assertEquals(HttpStatusCode.UnprocessableEntity, client.get("/v1/operations/nope").status)
        val vmId = requireNotNull(Regex("[0-9a-f-]{36}").find(client.get("/v1/virtualMachines").bodyAsText())).value
        assertEquals(HttpStatusCode.Conflict, client.post("/v1/virtualMachines/$vmId:start").status)
    }
}
