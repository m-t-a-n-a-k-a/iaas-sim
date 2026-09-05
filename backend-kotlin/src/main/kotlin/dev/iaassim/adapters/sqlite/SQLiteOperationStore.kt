package dev.iaassim.adapters.sqlite

import dev.iaassim.application.BackendOperationRef
import dev.iaassim.application.OperationNotFound
import dev.iaassim.application.OperationPersistenceFailure
import dev.iaassim.application.OperationStoreError
import dev.iaassim.application.OperationStorePort
import dev.iaassim.application.StoredOperation
import dev.iaassim.domain.ResourceReference
import dev.iaassim.domain.entity.operation.Failed
import dev.iaassim.domain.entity.operation.Operation
import dev.iaassim.domain.entity.operation.OperationFailure
import dev.iaassim.domain.entity.operation.OperationId
import dev.iaassim.domain.entity.operation.Running
import dev.iaassim.domain.entity.operation.Succeeded
import dev.iaassim.domain.entity.operation.isTerminal
import dev.iaassim.result.Err
import dev.iaassim.result.Ok
import dev.iaassim.result.Outcome
import java.nio.file.Path
import java.sql.Connection
import java.sql.DriverManager
import java.sql.ResultSet
import java.sql.SQLException
import java.util.UUID

class SQLiteOperationStore(private val path: Path = Path.of(System.getenv("IAAS_SIM_DB_PATH") ?: "iaas-sim.db")) :
    OperationStorePort {
    private val schema = SQLiteSchema(path)
    init { schema.initialize() }

    private fun connection(): Connection = schema.connection()

    override fun createRunning(operation: Operation, backendRef: BackendOperationRef):
        Outcome<Operation, OperationPersistenceFailure> {
        if (operation.status != Running) return Err(OperationPersistenceFailure("create", "operation must be RUNNING"))
        return write("create") { connection ->
            connection.prepareStatement("INSERT INTO operation VALUES (?, ?, ?, ?, 'RUNNING', NULL, ?)").use { statement ->
                statement.setString(1, operation.id.value.toString())
                statement.setString(2, operation.target.resourceType)
                statement.setString(3, operation.target.id)
                statement.setString(4, operation.action)
                statement.setString(5, backendRef.value)
                statement.executeUpdate()
            }
            operation
        }
    }

    override fun get(operationId: OperationId): Outcome<StoredOperation, OperationStoreError> = try {
        connection().use { connection -> connection.prepareStatement("SELECT * FROM operation WHERE id = ?").use { statement ->
            statement.setString(1, operationId.value.toString())
            statement.executeQuery().use { rows ->
                if (!rows.next()) Err(OperationNotFound(operationId)) else decode(rows)
            }
        } }
    } catch (exception: SQLException) { Err(OperationPersistenceFailure("get", exception.message ?: "database error")) }

    override fun complete(operation: Operation): Outcome<Operation, OperationStoreError> {
        if (!isTerminal(operation.status)) return Err(OperationPersistenceFailure("complete", "operation must be terminal"))
        val state: String
        val failure: String?
        when (val status = operation.status) {
            Running -> error("unreachable")
            Succeeded -> { state = "SUCCEEDED"; failure = null }
            is Failed -> { state = "FAILED"; failure = status.failure.reason }
        }
        val writeResult = write("complete") { connection ->
            connection.prepareStatement("UPDATE operation SET state = ?, failure_reason = ? WHERE id = ? AND state = 'RUNNING'").use { statement ->
                statement.setString(1, state); statement.setString(2, failure); statement.setString(3, operation.id.value.toString())
                statement.executeUpdate()
            }
        }
        if (writeResult is Err) return writeResult
        return when (val current = get(operation.id)) {
            is Err -> current
            is Ok -> Ok(current.value.operation)
        }
    }

    private fun decode(row: ResultSet): Outcome<StoredOperation, OperationPersistenceFailure> = try {
        val uuid = UUID.fromString(row.getString("id"))
        if (uuid.version() != 7) return Err(OperationPersistenceFailure("decode", "operation ID is not UUIDv7"))
        val reason = row.getString("failure_reason")
        val status = when (row.getString("state")) {
            "RUNNING" -> if (reason == null) Running else return malformed()
            "SUCCEEDED" -> if (reason == null) Succeeded else return malformed()
            "FAILED" -> if (reason != null) Failed(OperationFailure(reason)) else return malformed()
            else -> return malformed()
        }
        Ok(StoredOperation(Operation(OperationId(uuid), ResourceReference(row.getString("target_resource_type"),
            row.getString("target_resource_id")), row.getString("action"), status), BackendOperationRef(row.getString("backend_ref"))))
    } catch (exception: Exception) { Err(OperationPersistenceFailure("decode", exception.message ?: "malformed row")) }

    private fun malformed() = Err(OperationPersistenceFailure("decode", "malformed state/failure combination"))

    private fun <T> write(operation: String, block: (Connection) -> T): Outcome<T, OperationPersistenceFailure> = try {
        connection().use { connection ->
            connection.autoCommit = false
            try { val value = block(connection); connection.commit(); Ok(value) }
            catch (exception: SQLException) { connection.rollback(); Err(OperationPersistenceFailure(operation, exception.message ?: "database error")) }
        }
    } catch (exception: SQLException) { Err(OperationPersistenceFailure(operation, exception.message ?: "database error")) }
}
