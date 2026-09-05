package dev.iaassim

import dev.iaassim.adapters.identity.InMemoryVirtualMachineIdentityAdapter
import dev.iaassim.adapters.vsphere.VSphereAdapter
import dev.iaassim.adapters.sqlite.SQLiteOperationStore
import com.github.f4b6a3.uuid.UuidCreator
import dev.iaassim.application.BackendOperationPort
import dev.iaassim.application.GetOperationError
import dev.iaassim.application.OperationNotFound
import dev.iaassim.application.OperationPersistenceFailure
import dev.iaassim.application.OperationPollingFailure
import dev.iaassim.application.OperationStorePort
import dev.iaassim.application.PowerCommandConflict
import dev.iaassim.application.PowerCommandExecutionError
import dev.iaassim.application.PowerCommandIdentityFailure
import dev.iaassim.application.PowerCommandObservationFailure
import dev.iaassim.application.PowerCommandOperationPersistenceFailure
import dev.iaassim.application.PowerCommandSubmissionFailure
import dev.iaassim.application.PowerCommandVirtualMachineNotFound
import dev.iaassim.application.getOperation
import dev.iaassim.application.startVirtualMachine
import dev.iaassim.application.stopVirtualMachine
import dev.iaassim.domain.entity.operation.Failed
import dev.iaassim.domain.entity.operation.Operation
import dev.iaassim.domain.entity.operation.OperationId
import dev.iaassim.domain.entity.operation.Running
import dev.iaassim.domain.entity.operation.Succeeded
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
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import java.util.UUID

data class VirtualMachineDependencies(
    val port: VirtualMachinePort,
    val identity: VirtualMachineIdentityPort,
    val operations: OperationStorePort,
    val backendOperations: BackendOperationPort,
)

private fun defaultDependencies(): VirtualMachineDependencies {
    val adapter = VSphereAdapter()
    return VirtualMachineDependencies(adapter, InMemoryVirtualMachineIdentityAdapter(), SQLiteOperationStore(), adapter)
}

data class VirtualMachineResponse(val id: String, val name: String, val powerState: String)
data class VirtualMachineListResponse(val items: List<VirtualMachineResponse>)
data class ErrorResponse(val detail: String)
data class ResourceReferenceResponse(val resourceType: String, val id: String)
data class OperationFailureResponse(val reason: String)
data class OperationResponse(val id: String, val target: ResourceReferenceResponse, val action: String,
    val state: String, val failure: OperationFailureResponse?)

fun Application.module(
    dependencies: VirtualMachineDependencies = defaultDependencies(),
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
        post("/v1/virtualMachines/{virtualMachineId}:start") { powerCommand(dependencies, true) }
        post("/v1/virtualMachines/{virtualMachineId}:stop") { powerCommand(dependencies, false) }
        get("/v1/operations/{operationId}") {
            val id = parseOperationId(call.parameters["operationId"])
            if (id == null) {
                call.respond(HttpStatusCode.UnprocessableEntity, ErrorResponse("Operation ID must be UUIDv7")); return@get
            }
            when (val result = getOperation(dependencies.operations, dependencies.backendOperations, id)) {
                is Ok -> call.respond(operationResponse(result.value))
                is Err -> respondOperationError(result.error)
            }
        }
    }
}

private fun response(vm: VirtualMachine) = VirtualMachineResponse(vm.id.value.toString(), vm.name, vm.powerState.name)

private fun parseId(value: String?): VirtualMachineId? {
    val uuid = try { UUID.fromString(value) } catch (_: IllegalArgumentException) { return null }
    return if (uuid.version() == 7) VirtualMachineId(uuid) else null
}

private fun parseOperationId(value: String?): OperationId? {
    val uuid = try { UUID.fromString(value) } catch (_: IllegalArgumentException) { return null }
    return if (uuid.version() == 7) OperationId(uuid) else null
}

private fun operationResponse(operation: Operation): OperationResponse {
    val (state, failure) = when (val status = operation.status) {
        Running -> "RUNNING" to null
        Succeeded -> "SUCCEEDED" to null
        is Failed -> "FAILED" to OperationFailureResponse(status.failure.reason)
    }
    return OperationResponse(operation.id.value.toString(), ResourceReferenceResponse(operation.target.resourceType,
        operation.target.id), operation.action, state, failure)
}

private suspend fun io.ktor.server.routing.RoutingContext.powerCommand(
    dependencies: VirtualMachineDependencies, start: Boolean,
) {
    val id = parseId(call.parameters["virtualMachineId"])
    if (id == null) { call.respond(HttpStatusCode.UnprocessableEntity,
        ErrorResponse("VirtualMachine ID must be UUIDv7")); return }
    val operationId = OperationId(UuidCreator.getTimeOrderedEpoch())
    val result = if (start) startVirtualMachine(dependencies.port, dependencies.identity, dependencies.operations, id, operationId)
        else stopVirtualMachine(dependencies.port, dependencies.identity, dependencies.operations, id, operationId)
    when (result) {
        is Ok -> { call.response.headers.append("Location", "/v1/operations/${result.value.id.value}")
            call.respond(HttpStatusCode.Accepted, operationResponse(result.value)) }
        is Err -> respondCommandError(result.error, start)
    }
}

private suspend fun io.ktor.server.routing.RoutingContext.respondCommandError(error: PowerCommandExecutionError, start: Boolean) {
    when (error) {
        is PowerCommandVirtualMachineNotFound -> call.respond(HttpStatusCode.NotFound, ErrorResponse("VirtualMachine not found"))
        is PowerCommandConflict -> call.respond(HttpStatusCode.Conflict,
            ErrorResponse(if (start) "VirtualMachine is already running" else "VirtualMachine is already stopped"))
        is PowerCommandObservationFailure -> call.respond(HttpStatusCode.BadGateway, ErrorResponse("VirtualMachine backend request failed"))
        is PowerCommandSubmissionFailure -> call.respond(HttpStatusCode.BadGateway, ErrorResponse("VirtualMachine power command submission failed"))
        is PowerCommandIdentityFailure -> call.respond(HttpStatusCode.InternalServerError, ErrorResponse("VirtualMachine identity persistence failed"))
        is PowerCommandOperationPersistenceFailure -> call.respond(HttpStatusCode.InternalServerError, ErrorResponse("Operation persistence failed"))
    }
}

private suspend fun io.ktor.server.routing.RoutingContext.respondOperationError(error: GetOperationError) {
    when (error) {
        is OperationNotFound -> call.respond(HttpStatusCode.NotFound, ErrorResponse("Operation not found"))
        is OperationPollingFailure -> call.respond(HttpStatusCode.BadGateway, ErrorResponse("Operation polling failed"))
        is OperationPersistenceFailure -> call.respond(HttpStatusCode.InternalServerError, ErrorResponse("Operation persistence failed"))
    }
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
