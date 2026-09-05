package dev.iaassim.adapters.sqlite

import com.github.f4b6a3.uuid.UuidCreator
import dev.iaassim.application.*
import dev.iaassim.domain.entity.instancetype.*
import dev.iaassim.result.*
import java.nio.file.Path
import java.sql.ResultSet
import java.util.UUID

class SQLiteInstanceTypeStore(private val path: Path = Path.of(System.getenv("IAAS_SIM_DB_PATH") ?: "iaas-sim.db")) : InstanceTypeStorePort {
    private val schema = SQLiteSchema(path)
    init { schema.initialize(); seed() }
    private fun seed() = schema.connection().use { c ->
        c.prepareStatement("INSERT INTO instance_type VALUES (?, ?, ?, ?) ON CONFLICT(name) DO NOTHING").use { s ->
            listOf(Triple("small", 1, 1024), Triple("medium", 2, 2048), Triple("large", 4, 4096)).forEach { (name, cpu, memory) ->
                s.setString(1, UuidCreator.getTimeOrderedEpoch().toString()); s.setString(2, name)
                s.setInt(3, cpu); s.setInt(4, memory); s.executeUpdate()
            }
        }
    }
    override fun listInstanceTypes(): Outcome<List<InstanceType>, InstanceTypePersistenceFailure> = try {
        schema.connection().use { c -> c.createStatement().executeQuery("SELECT * FROM instance_type ORDER BY name").use { rows ->
            val values = mutableListOf<InstanceType>(); while (rows.next()) values.add(decode(rows)); Ok(values)
        } }
    } catch (e: Exception) { Err(failure("list", e)) }
    override fun getInstanceType(instanceTypeId: InstanceTypeId): Outcome<InstanceType, InstanceTypeStoreError> = try {
        schema.connection().use { c -> c.prepareStatement("SELECT * FROM instance_type WHERE id = ?").use { s ->
            s.setString(1, instanceTypeId.value.toString()); s.executeQuery().use { rows ->
                if (!rows.next()) Err(InstanceTypeNotFound(instanceTypeId)) else Ok(decode(rows))
            }
        } }
    } catch (e: Exception) { Err(failure("get", e)) }
    private fun decode(row: ResultSet): InstanceType {
        val uuid = UUID.fromString(row.getString("id")); require(uuid.version() == 7) { "InstanceType ID is not UUIDv7" }
        val name = row.getString("name"); val cpu = row.getInt("vcpus"); val memory = row.getInt("memory_mib")
        require(cpu > 0 && memory > 0) { "invalid InstanceType sizing" }
        return InstanceType(InstanceTypeId(uuid), name, cpu, memory)
    }
    private fun failure(op: String, e: Exception) = InstanceTypePersistenceFailure(op, e.message ?: "database error")
}
