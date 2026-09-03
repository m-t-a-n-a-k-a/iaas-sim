import sqlite3
from pathlib import Path
from uuid import UUID, uuid7

from iaas_sim.adapters.sqlite.adapter import SQLiteAdapter
from iaas_sim.adapters.sqlite.migration import SCHEMA_VERSION, migrate_database
from iaas_sim.adapters.sqlite.operation import SQLiteOperationStore
from iaas_sim.adapters.sqlite.virtual_machine_create import SQLiteVirtualMachineCreateFinalizer
from iaas_sim.application.identity import BackendVirtualMachineRef
from iaas_sim.application.operation import BackendOperationRef, OperationPersistenceFailure
from iaas_sim.domain.entity.operation import Operation, OperationId, Running, Succeeded
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok


def running_create(vm_id: VirtualMachineId) -> Operation:
    return Operation(
        OperationId(uuid7()), ResourceReference("virtualMachines", str(vm_id)), "CREATE", Running()
    )


def test_atomic_finalization_and_exact_retry_keep_schema_v3(tmp_path: Path) -> None:
    path = tmp_path / "control-plane.db"
    migrate_database(path)
    vm_id = VirtualMachineId(uuid7())
    operation = running_create(vm_id)
    store = SQLiteOperationStore(path)
    assert store.create_running(operation, BackendOperationRef("task-1")) == Ok(operation)
    finalizer = SQLiteVirtualMachineCreateFinalizer(path)

    expected = Operation(operation.id, operation.target, operation.action, Succeeded())
    assert finalizer.finalize_virtual_machine_create(
        operation, vm_id, BackendVirtualMachineRef("vm-42")
    ) == Ok(expected)
    assert finalizer.finalize_virtual_machine_create(
        operation, vm_id, BackendVirtualMachineRef("vm-42")
    ) == Ok(expected)
    assert SQLiteAdapter(path).get_backend_ref(vm_id) == Ok(BackendVirtualMachineRef("vm-42"))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)


def test_identity_conflict_rolls_back_operation_transition(tmp_path: Path) -> None:
    path = tmp_path / "control-plane.db"
    migrate_database(path)
    first_id = VirtualMachineId(uuid7())
    operation = running_create(first_id)
    store = SQLiteOperationStore(path)
    assert store.create_running(operation, BackendOperationRef("task-1")) == Ok(operation)
    other = running_create(VirtualMachineId(uuid7()))
    assert store.create_running(other, BackendOperationRef("task-2")) == Ok(other)
    finalizer = SQLiteVirtualMachineCreateFinalizer(path)
    assert isinstance(
        finalizer.finalize_virtual_machine_create(
            operation, first_id, BackendVirtualMachineRef("vm-conflict")
        ),
        Ok,
    )

    result = finalizer.finalize_virtual_machine_create(
        other,
        VirtualMachineId(UUID(other.target.resource_id)),
        BackendVirtualMachineRef("vm-conflict"),
    )
    assert isinstance(result, Err)
    assert isinstance(result.error, OperationPersistenceFailure)
    loaded = store.get(other.id)
    assert isinstance(loaded, Ok)
    assert isinstance(loaded.value.operation.status, Running)
