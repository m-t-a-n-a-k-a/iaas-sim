package dev.iaassim.adapters.sqlite

import dev.iaassim.application.*
import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.operation.*
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.*
import java.nio.file.Path
import java.sql.Connection
import java.util.UUID

class SQLiteVirtualMachineCreateFinalizer(private val path: Path = Path.of(System.getenv("IAAS_SIM_DB_PATH") ?: "iaas-sim.db")) :
    VirtualMachineCreateFinalizerPort {
    private val schema = SQLiteSchema(path)
    init { schema.initialize() }
    override fun finalizeVirtualMachineCreate(operation: Operation, virtualMachineId: VirtualMachineId,
        backendRef: BackendVirtualMachineRef): Outcome<Operation, OperationPersistenceFailure> = try {
        schema.connection().use { c -> c.autoCommit = false
            try { val value = finalize(c, operation, virtualMachineId, backendRef); c.commit(); Ok(value) }
            catch (e: Exception) { c.rollback(); Err(OperationPersistenceFailure("finalize-vm-create", e.message ?: "database error")) }
        }
    } catch (e: Exception) { Err(OperationPersistenceFailure("finalize-vm-create", e.message ?: "database error")) }

    private fun finalize(c: Connection, requested: Operation, vmId: VirtualMachineId, backendRef: BackendVirtualMachineRef): Operation {
        val current = c.prepareStatement("SELECT * FROM operation WHERE id = ?").use { s ->
            s.setString(1, requested.id.value.toString()); s.executeQuery().use { r ->
                require(r.next()) { "operation not found" }
                val status = when (r.getString("state")) {
                    "RUNNING" -> Running; "SUCCEEDED" -> Succeeded
                    "FAILED" -> Failed(OperationFailure(requireNotNull(r.getString("failure_reason"))))
                    else -> error("malformed operation")
                }
                Operation(requested.id, ResourceReference(r.getString("target_resource_type"), r.getString("target_resource_id")), r.getString("action"), status)
            }
        }
        require(current.target.resourceType == "virtualMachines" && current.target.id == vmId.value.toString() && current.action == "CREATE") {
            "operation does not describe this VM create"
        }
        if (current.status is Failed) return current
        val byId = lookup(c, "id", vmId.value.toString())
        val byRef = lookup(c, "backend_ref", backendRef.value)
        val exact = byId == Pair(vmId.value.toString(), backendRef.value) && byRef == byId
        if (current.status == Succeeded) { require(exact) { "VM identity mapping conflict" }; return current }
        require((byId == null && byRef == null) || exact) { "VM identity mapping conflict" }
        if (!exact) c.prepareStatement("INSERT INTO virtual_machine VALUES (?, ?)").use { s ->
            s.setString(1, vmId.value.toString()); s.setString(2, backendRef.value); s.executeUpdate()
        }
        val changed = c.prepareStatement("UPDATE operation SET state='SUCCEEDED', failure_reason=NULL WHERE id=? AND state='RUNNING'").use { s ->
            s.setString(1, requested.id.value.toString()); s.executeUpdate()
        }
        require(changed == 1) { "operation transition failed" }
        return current.copy(status = Succeeded)
    }
    private fun lookup(c: Connection, column: String, value: String): Pair<String, String>? =
        c.prepareStatement("SELECT id, backend_ref FROM virtual_machine WHERE $column = ?").use { s ->
            s.setString(1, value); s.executeQuery().use { r -> if (r.next()) Pair(r.getString(1), r.getString(2)) else null }
        }
}
