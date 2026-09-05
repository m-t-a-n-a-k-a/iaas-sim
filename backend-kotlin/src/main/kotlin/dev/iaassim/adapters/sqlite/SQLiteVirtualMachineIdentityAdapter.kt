package dev.iaassim.adapters.sqlite

import com.github.f4b6a3.uuid.UuidCreator
import dev.iaassim.application.*
import dev.iaassim.domain.entity.virtualmachine.VirtualMachineId
import dev.iaassim.result.*
import java.nio.file.Path
import java.sql.SQLException
import java.util.UUID

class SQLiteVirtualMachineIdentityAdapter(private val path: Path = Path.of(System.getenv("IAAS_SIM_DB_PATH") ?: "iaas-sim.db")) :
    VirtualMachineIdentityPort {
    private val schema = SQLiteSchema(path)
    init { schema.initialize() }

    override fun findByBackendRef(backendRef: BackendVirtualMachineRef): Outcome<VirtualMachineId?, VirtualMachineIdentityPersistenceFailure> =
        try { schema.connection().use { c -> c.prepareStatement("SELECT id FROM virtual_machine WHERE backend_ref = ?").use { s ->
            s.setString(1, backendRef.value); s.executeQuery().use { rows -> Ok(if (rows.next()) decode(rows.getString(1)) else null) }
        } } } catch (e: Exception) { Err(failure("find", e)) }

    override fun getOrCreateByBackendRef(backendRef: BackendVirtualMachineRef): Outcome<VirtualMachineId, VirtualMachineIdentityPersistenceFailure> =
        try { schema.connection().use { c ->
            c.prepareStatement("INSERT INTO virtual_machine(id, backend_ref) VALUES (?, ?) ON CONFLICT(backend_ref) DO NOTHING").use { s ->
                s.setString(1, UuidCreator.getTimeOrderedEpoch().toString()); s.setString(2, backendRef.value); s.executeUpdate()
            }
            c.prepareStatement("SELECT id FROM virtual_machine WHERE backend_ref = ?").use { s ->
                s.setString(1, backendRef.value); s.executeQuery().use { rows ->
                    if (!rows.next()) Err(VirtualMachineIdentityPersistenceFailure("get-or-create", "identity row unavailable"))
                    else Ok(decode(rows.getString(1)))
                }
            }
        } } catch (e: Exception) { Err(failure("get-or-create", e)) }

    override fun getBackendRef(virtualMachineId: VirtualMachineId): Outcome<BackendVirtualMachineRef, VirtualMachineIdentityError> =
        try { schema.connection().use { c -> c.prepareStatement("SELECT backend_ref FROM virtual_machine WHERE id = ?").use { s ->
            s.setString(1, virtualMachineId.value.toString()); s.executeQuery().use { rows ->
                if (rows.next()) Ok(BackendVirtualMachineRef(rows.getString(1))) else Err(VirtualMachineIdentityNotFound(virtualMachineId))
            }
        } } } catch (e: SQLException) { Err(failure("get", e)) }

    private fun decode(raw: String): VirtualMachineId {
        val uuid = UUID.fromString(raw)
        require(uuid.version() == 7) { "virtual machine ID is not UUIDv7" }
        return VirtualMachineId(uuid)
    }
    private fun failure(operation: String, e: Exception) =
        VirtualMachineIdentityPersistenceFailure(operation, e.message ?: "database error")
}
