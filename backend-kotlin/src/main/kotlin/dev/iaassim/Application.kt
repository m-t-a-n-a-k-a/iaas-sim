package dev.iaassim

import dev.iaassim.adapters.identity.InMemoryVirtualMachineIdentityAdapter
import dev.iaassim.adapters.vsphere.VSphereAdapter
import dev.iaassim.application.VirtualMachineBackendFailure
import dev.iaassim.application.VirtualMachineIdentityPersistenceFailure
import dev.iaassim.application.VirtualMachineIdentityPort
import dev.iaassim.application.VirtualMachineNotFound
import dev.iaassim.application.VirtualMachinePort
import dev.iaassim.application.VirtualMachineReadError
import dev.iaassim.application.getVirtualMachine
import dev.iaassim.application.listVirtualMachines
import dev.iaassim.domain.entity.virtualmachine.VirtualMachine
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.jackson.jackson
import io.ktor.server.application.Application
import io.ktor.server.application.call
import io.ktor.server.application.install
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.response.respond
import io.ktor.server.routing.get
import io.ktor.server.routing.routing
import java.util.UUID

data class VirtualMachineDependencies(
    val port: VirtualMachinePort,
    val identity: VirtualMachineIdentityPort,
)

data class VirtualMachineResponse(val id: String, val name: String, val powerState: String)
data class VirtualMachineListResponse(val items: List<VirtualMachineResponse>)
data class ErrorResponse(val detail: String)

fun Application.module(
    dependencies: VirtualMachineDependencies = VirtualMachineDependencies(
        VSphereAdapter(),
        InMemoryVirtualMachineIdentityAdapter(),
    ),
) {
    install(ContentNegotiation) { jackson() }
    routing {
        get("/health") { call.respond(mapOf("status" to "ok")) }
        get("/v1/virtualMachines") {
            when (val result = listVirtualMachines(dependencies.port, dependencies.identity)) {
                is Ok -> call.respond(VirtualMachineListResponse(result.value.map(::response)))
                is Err -> respondError(result.error)
            }
        }
        get("/v1/virtualMachines/{virtualMachineId}") {
            val id = parseId(call.parameters["virtualMachineId"])
            if (id == null) {
                call.respond(HttpStatusCode.UnprocessableEntity, ErrorResponse("VirtualMachine ID must be UUIDv7"))
                return@get
            }
            when (val result = getVirtualMachine(dependencies.port, dependencies.identity, id)) {
                is Ok -> call.respond(response(result.value))
                is Err -> respondError(result.error)
            }
        }
    }
}

private fun response(vm: VirtualMachine) = VirtualMachineResponse(vm.id.value.toString(), vm.name, vm.powerState.name)

private fun parseId(value: String?): VirtualMachineId? {
    val uuid = try { UUID.fromString(value) } catch (_: IllegalArgumentException) { return null }
    return if (uuid.version() == 7) VirtualMachineId(uuid) else null
}

private suspend fun io.ktor.server.routing.RoutingContext.respondError(error: VirtualMachineReadError) {
    when (error) {
        is VirtualMachineNotFound -> call.respond(HttpStatusCode.NotFound, ErrorResponse("VirtualMachine not found"))
        is VirtualMachineBackendFailure -> call.respond(HttpStatusCode.BadGateway, ErrorResponse("VirtualMachine backend request failed"))
        is VirtualMachineIdentityPersistenceFailure -> call.respond(HttpStatusCode.InternalServerError, ErrorResponse("VirtualMachine identity persistence failed"))
    }
}

fun main() {
    embeddedServer(Netty, host = "0.0.0.0", port = 8080, module = Application::module).start(wait = true)
}
