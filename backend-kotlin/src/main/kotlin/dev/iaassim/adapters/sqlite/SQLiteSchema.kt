package dev.iaassim.adapters.sqlite

import java.nio.file.Path
import java.sql.Connection
import java.sql.DriverManager

internal class SQLiteSchema(private val path: Path) {
    fun connection(): Connection = DriverManager.getConnection("jdbc:sqlite:${path.toAbsolutePath()}")

    fun initialize() = connection().use { connection -> connection.createStatement().use { statement ->
        statement.executeUpdate("""
            CREATE TABLE IF NOT EXISTS operation (
              id TEXT PRIMARY KEY, target_resource_type TEXT NOT NULL, target_resource_id TEXT NOT NULL,
              action TEXT NOT NULL, state TEXT NOT NULL, failure_reason TEXT, backend_ref TEXT NOT NULL,
              CHECK (state IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
              CHECK ((state = 'FAILED' AND failure_reason IS NOT NULL) OR (state <> 'FAILED' AND failure_reason IS NULL))
            ) STRICT
        """.trimIndent())
        statement.executeUpdate("CREATE TABLE IF NOT EXISTS virtual_machine (id TEXT PRIMARY KEY, backend_ref TEXT NOT NULL UNIQUE) STRICT")
        statement.executeUpdate("""
            CREATE TABLE IF NOT EXISTS instance_type (
              id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
              vcpus INTEGER NOT NULL CHECK (vcpus > 0),
              memory_mib INTEGER NOT NULL CHECK (memory_mib > 0)
            ) STRICT
        """.trimIndent())
    } }
}
