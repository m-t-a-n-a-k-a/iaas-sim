# ruff: noqa: PLR2004
import sqlite3
from pathlib import Path
from uuid import uuid7

import pytest

from iaas_sim.adapters.sqlite.adapter import SQLiteAdapter
from iaas_sim.adapters.sqlite.connection import connect_database
from iaas_sim.adapters.sqlite.migration import SCHEMA_VERSION, migrate_database
from iaas_sim.adapters.sqlite.operation import SQLiteOperationStore
from iaas_sim.adapters.sqlite.virtual_machine_create import SQLiteVirtualMachineCreateFinalizer
from iaas_sim.application.identity import BackendVirtualMachineRef, VirtualMachineIdentityNotFound
from iaas_sim.application.operation import BackendOperationRef, OperationPersistenceFailure
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Running,
    Succeeded,
)
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok


def create_operation(path: Path, vm_id: VirtualMachineId, state: str = "RUNNING") -> Operation:
    operation = Operation(
        OperationId(uuid7()), ResourceReference("virtualMachines", str(vm_id)), "CREATE", Running()
    )
    assert SQLiteOperationStore(path).create_running(
        operation, BackendOperationRef("task-1")
    ) == Ok(operation)
    if state != "RUNNING":
        reason = "backend failed" if state == "FAILED" else None
        with connect_database(path) as connection:
            connection.execute(
                "UPDATE operation SET state = ?, failure_reason = ? WHERE id = ?",
                (state, reason, str(operation.id)),
            )
            connection.commit()
    return operation


def bind(path: Path, vm_id: VirtualMachineId, backend_ref: BackendVirtualMachineRef) -> None:
    with connect_database(path) as connection:
        connection.execute(
            "INSERT INTO virtual_machine (id, backend_ref) VALUES (?, ?)",
            (str(vm_id), str(backend_ref)),
        )
        connection.commit()


def operation_status(path: Path, operation: Operation) -> object:
    loaded = SQLiteOperationStore(path).get(operation.id)
    assert isinstance(loaded, Ok)
    return loaded.value.operation.status


def mappings(path: Path) -> list[tuple[str, str]]:
    with connect_database(path) as connection:
        return connection.execute(
            "SELECT id, backend_ref FROM virtual_machine ORDER BY id"
        ).fetchall()


def test_running_without_mapping_atomically_inserts_and_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "control-plane.db"
    migrate_database(path)
    vm_id = VirtualMachineId(uuid7())
    operation = create_operation(path, vm_id)

    result = SQLiteVirtualMachineCreateFinalizer(path).finalize_virtual_machine_create(
        operation, vm_id, BackendVirtualMachineRef("vm-42")
    )

    expected = Operation(operation.id, operation.target, operation.action, Succeeded())
    assert result == Ok(expected)
    assert SQLiteAdapter(path).get_backend_ref(vm_id) == Ok(BackendVirtualMachineRef("vm-42"))
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert SCHEMA_VERSION == 3


def test_running_with_exact_mapping_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "db"
    migrate_database(path)
    vm_id, backend_ref = VirtualMachineId(uuid7()), BackendVirtualMachineRef("vm-42")
    operation = create_operation(path, vm_id)
    bind(path, vm_id, backend_ref)

    result = SQLiteVirtualMachineCreateFinalizer(path).finalize_virtual_machine_create(
        operation, vm_id, backend_ref
    )

    assert result == Ok(Operation(operation.id, operation.target, operation.action, Succeeded()))
    assert mappings(path) == [(str(vm_id), str(backend_ref))]


@pytest.mark.parametrize("conflict", ["public-id", "backend-ref"])
def test_running_conflict_leaves_operation_and_mappings_unchanged(
    conflict: str, tmp_path: Path
) -> None:
    path = tmp_path / "db"
    migrate_database(path)
    vm_id, backend_ref = VirtualMachineId(uuid7()), BackendVirtualMachineRef("vm-wanted")
    operation = create_operation(path, vm_id)
    if conflict == "public-id":
        bind(path, vm_id, BackendVirtualMachineRef("vm-other"))
    else:
        bind(path, VirtualMachineId(uuid7()), backend_ref)
    before = mappings(path)

    result = SQLiteVirtualMachineCreateFinalizer(path).finalize_virtual_machine_create(
        operation, vm_id, backend_ref
    )

    assert isinstance(result, Err)
    assert isinstance(result.error, OperationPersistenceFailure)
    assert isinstance(operation_status(path, operation), Running)
    assert mappings(path) == before


@pytest.mark.parametrize("mapping", ["absent", "public-id-conflict", "backend-ref-conflict"])
def test_succeeded_requires_exact_bidirectional_mapping(mapping: str, tmp_path: Path) -> None:
    path = tmp_path / "db"
    migrate_database(path)
    vm_id, backend_ref = VirtualMachineId(uuid7()), BackendVirtualMachineRef("vm-wanted")
    operation = create_operation(path, vm_id, "SUCCEEDED")
    if mapping == "public-id-conflict":
        bind(path, vm_id, BackendVirtualMachineRef("vm-other"))
    elif mapping == "backend-ref-conflict":
        bind(path, VirtualMachineId(uuid7()), backend_ref)

    result = SQLiteVirtualMachineCreateFinalizer(path).finalize_virtual_machine_create(
        operation, vm_id, backend_ref
    )

    assert isinstance(result, Err)
    assert isinstance(operation_status(path, operation), Succeeded)


def test_succeeded_with_exact_mapping_returns_existing_operation(tmp_path: Path) -> None:
    path = tmp_path / "db"
    migrate_database(path)
    vm_id, backend_ref = VirtualMachineId(uuid7()), BackendVirtualMachineRef("vm-42")
    operation = create_operation(path, vm_id, "SUCCEEDED")
    bind(path, vm_id, backend_ref)

    result = SQLiteVirtualMachineCreateFinalizer(path).finalize_virtual_machine_create(
        operation, vm_id, backend_ref
    )

    assert result == Ok(Operation(operation.id, operation.target, operation.action, Succeeded()))


@pytest.mark.parametrize("with_conflict", [False, True], ids=["no-mapping", "external-conflict"])
def test_failed_never_materializes_identity_or_changes_state(
    with_conflict: bool, tmp_path: Path
) -> None:
    path = tmp_path / "db"
    migrate_database(path)
    vm_id, backend_ref = VirtualMachineId(uuid7()), BackendVirtualMachineRef("vm-wanted")
    operation = create_operation(path, vm_id, "FAILED")
    if with_conflict:
        bind(path, VirtualMachineId(uuid7()), backend_ref)
    before = mappings(path)

    result = SQLiteVirtualMachineCreateFinalizer(path).finalize_virtual_machine_create(
        operation, vm_id, backend_ref
    )

    assert result == Ok(
        Operation(
            operation.id,
            operation.target,
            operation.action,
            Failed(OperationFailure("backend failed")),
        )
    )
    assert isinstance(operation_status(path, operation), Failed)
    assert mappings(path) == before
    assert SQLiteAdapter(path).get_backend_ref(vm_id) == Err(VirtualMachineIdentityNotFound(vm_id))
