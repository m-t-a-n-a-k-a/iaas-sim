# ruff: noqa: PLR2004
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid7

import pytest

from iaas_sim.adapters.sqlite.adapter import SQLiteAdapter
from iaas_sim.adapters.sqlite.connection import connect_database, transaction
from iaas_sim.adapters.sqlite.migration import SCHEMA_VERSION, migrate_database
from iaas_sim.application.identity import (
    BackendSnapshotRef,
    BackendVirtualMachineRef,
    SnapshotIdentityNotFound,
    SnapshotIdentityOwnerMismatch,
    VirtualMachineIdentityNotFound,
)
from iaas_sim.domain.entity.snapshot import SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Err, Ok


def _database_path(tmp_path: Path) -> Path:
    return tmp_path / "control-plane.db"


def test_migration_creates_versioned_schema_and_is_idempotent(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)

    migrate_database(database_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version == SCHEMA_VERSION
    assert {"virtual_machine", "snapshot"} <= tables


def test_connections_enable_foreign_keys(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connection_is_queryable_inside_context_and_closed_after_exit(
    tmp_path: Path,
) -> None:
    with connect_database(_database_path(tmp_path)) as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_connection_is_closed_when_context_exits_with_exception(tmp_path: Path) -> None:
    opened_connections: list[sqlite3.Connection] = []
    with (
        pytest.raises(RuntimeError, match="context failure"),
        connect_database(_database_path(tmp_path)) as connection,
    ):
        opened_connections.append(connection)
        raise RuntimeError("context failure")

    closed_connection = opened_connections[0]
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        closed_connection.execute("SELECT 1")


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection, transaction(connection):
        connection.execute(
            "INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)",
            ("vm-1", "backend-vm-1"),
        )

    with connect_database(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM virtual_machine").fetchone()[0] == 1


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection:
        with (
            pytest.raises(RuntimeError, match="transaction failure"),
            transaction(connection),
        ):
            connection.execute(
                "INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)",
                ("vm-1", "backend-vm-1"),
            )
            raise RuntimeError("transaction failure")

        assert connection.execute("SELECT COUNT(*) FROM virtual_machine").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("table", "first_values", "duplicate_values"),
    [
        pytest.param(
            "virtual_machine",
            ("vm-1", "backend-vm-1"),
            ("vm-2", "backend-vm-1"),
            id="duplicate-virtual-machine-backend-ref",
        ),
        pytest.param(
            "snapshot",
            ("snapshot-1", "backend-snapshot-1", "vm-1"),
            ("snapshot-2", "backend-snapshot-1", "vm-1"),
            id="duplicate-snapshot-backend-ref",
        ),
    ],
)
def test_backend_refs_are_unique(
    tmp_path: Path,
    table: str,
    first_values: tuple[str, ...],
    duplicate_values: tuple[str, ...],
) -> None:
    database_path = _database_path(tmp_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection:
        columns = (
            "id, backend_ref"
            if table == "virtual_machine"
            else "id, backend_ref, virtual_machine_id"
        )
        if table == "snapshot":
            connection.execute(
                "INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)",
                ("vm-1", "backend-vm-1"),
            )
        first_placeholders = ", ".join("?" for _ in first_values)
        connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({first_placeholders})",
            first_values,
        )
        with pytest.raises(sqlite3.IntegrityError):
            placeholders = ", ".join("?" for _ in duplicate_values)
            connection.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                duplicate_values,
            )


def test_snapshot_requires_an_existing_virtual_machine(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO snapshot (id, backend_ref, virtual_machine_id) VALUES (?, ?, ?)",
            ("snapshot-1", "backend-snapshot-1", "unknown-vm"),
        )


def test_valid_relationship_index_and_file_persistence(tmp_path: Path) -> None:
    database_path = _database_path(tmp_path)
    migrate_database(database_path)

    with connect_database(database_path) as connection:
        with transaction(connection):
            connection.execute(
                "INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)",
                ("vm-1", "backend-vm-1"),
            )
            connection.execute(
                "INSERT INTO snapshot (id, backend_ref, virtual_machine_id) VALUES (?, ?, ?)",
                ("snapshot-1", "backend-snapshot-1", "vm-1"),
            )
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(snapshot)").fetchall()}

    with connect_database(database_path) as reopened_connection:
        persisted_owner = reopened_connection.execute(
            "SELECT virtual_machine_id FROM snapshot WHERE id = ?", ("snapshot-1",)
        ).fetchone()[0]

    assert "snapshot_virtual_machine_id_idx" in indexes
    assert persisted_owner == "vm-1"


def test_vm_identity_mapping_is_uuid7_stable_distinct_and_reversible(tmp_path: Path) -> None:
    path = _database_path(tmp_path)
    migrate_database(path)
    adapter = SQLiteAdapter(path)
    first = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-1"))
    repeated = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-1"))
    other = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-2"))
    assert isinstance(first, Ok) and first.value.version == 7
    assert repeated == first and other != first
    assert adapter.get_backend_ref(first.value) == Ok(BackendVirtualMachineRef("vm-1"))
    assert (
        SQLiteAdapter(path).get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-1")) == first
    )
    unknown = VirtualMachineId(uuid7())
    assert adapter.get_backend_ref(unknown) == Err(VirtualMachineIdentityNotFound(unknown))


def test_invalid_stored_vm_uuid_is_typed_failure(tmp_path: Path) -> None:
    path = _database_path(tmp_path)
    migrate_database(path)
    with connect_database(path) as connection:
        connection.execute(
            "INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)", ("not-a-uuid", "vm-bad")
        )
        connection.commit()
    assert isinstance(
        SQLiteAdapter(path).get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-bad")), Err
    )


def test_snapshot_identity_is_uuid7_stable_distinct_reversible_and_persistent(
    tmp_path: Path,
) -> None:
    path = _database_path(tmp_path)
    migrate_database(path)
    adapter = SQLiteAdapter(path)
    owner = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-owner"))
    assert isinstance(owner, Ok)
    first = adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-1"), owner.value)
    repeated = adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-1"), owner.value)
    other = adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-2"), owner.value)
    assert isinstance(first, Ok) and first.value.version == 7
    assert repeated == first and other != first
    mapping = adapter.get_snapshot_mapping(first.value)
    assert isinstance(mapping, Ok)
    assert mapping.value.backend_ref == BackendSnapshotRef("snapshot-1")
    assert mapping.value.virtual_machine_id == owner.value
    assert (
        SQLiteAdapter(path).get_or_create_snapshot(BackendSnapshotRef("snapshot-1"), owner.value)
        == first
    )


def test_snapshot_owner_mismatch_is_typed_and_does_not_rewrite(tmp_path: Path) -> None:
    path = _database_path(tmp_path)
    migrate_database(path)
    adapter = SQLiteAdapter(path)
    first_owner = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-a"))
    second_owner = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-b"))
    assert isinstance(first_owner, Ok) and isinstance(second_owner, Ok)
    created = adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-1"), first_owner.value)
    assert isinstance(created, Ok)
    mismatch = adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-1"), second_owner.value)
    assert mismatch == Err(SnapshotIdentityOwnerMismatch(BackendSnapshotRef("snapshot-1")))
    mapping = adapter.get_snapshot_mapping(created.value)
    assert isinstance(mapping, Ok) and mapping.value.virtual_machine_id == first_owner.value


def test_snapshot_unknown_and_malformed_stored_ids_are_typed_failures(tmp_path: Path) -> None:
    path = _database_path(tmp_path)
    migrate_database(path)
    adapter = SQLiteAdapter(path)
    unknown = SnapshotId(uuid7())
    assert adapter.get_snapshot_mapping(unknown) == Err(SnapshotIdentityNotFound(unknown))
    owner = adapter.get_or_create_by_backend_ref(BackendVirtualMachineRef("vm-owner"))
    assert isinstance(owner, Ok)
    with connect_database(path) as connection:
        connection.execute(
            "INSERT INTO snapshot (id, backend_ref, virtual_machine_id) VALUES (?, ?, ?)",
            ("bad-id", "snapshot-bad-id", str(owner.value)),
        )
        connection.commit()
    # Simulate externally corrupted storage; production connections enforce the FK.
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO snapshot (id, backend_ref, virtual_machine_id) VALUES (?, ?, ?)",
            (str(uuid7()), "snapshot-bad-owner", "bad-owner"),
        )
    assert isinstance(
        adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-bad-id"), owner.value), Err
    )
    assert isinstance(
        adapter.get_or_create_snapshot(BackendSnapshotRef("snapshot-bad-owner"), owner.value), Err
    )
