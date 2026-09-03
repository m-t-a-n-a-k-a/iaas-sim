from pathlib import Path
from uuid import uuid4, uuid7

from iaas_sim.adapters.sqlite.connection import connect_database
from iaas_sim.adapters.sqlite.migration import migrate_database
from iaas_sim.adapters.sqlite.operation import SQLiteOperationStore
from iaas_sim.application.get_operation import BACKEND_OPERATION_FAILURE_REASON, get_operation
from iaas_sim.application.operation import (
    BackendOperationRef,
    BackendOperationStatus,
    BackendOperationSucceeded,
    OperationNotFound,
    OperationPersistenceFailure,
    OperationPollingFailure,
)
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    Running,
    Succeeded,
)
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result


def _operation() -> Operation:
    return Operation(
        OperationId(uuid7()), ResourceReference("virtualMachines", str(uuid7())), "START", Running()
    )


class CountingBackend:
    def __init__(self) -> None:
        self.calls = 0

    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]:
        assert backend_ref == BackendOperationRef("task-17")
        self.calls += 1
        return Ok(BackendOperationSucceeded())


def test_operation_roundtrip_restart_reconciliation_and_terminal_short_circuit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "db.sqlite"
    migrate_database(path)
    operation = _operation()
    assert SQLiteOperationStore(path).create_running(
        operation, BackendOperationRef("task-17")
    ) == Ok(operation)

    backend = CountingBackend()
    reconciled = get_operation(SQLiteOperationStore(path), backend, operation.id)
    assert reconciled == Ok(
        Operation(operation.id, operation.target, operation.action, Succeeded())
    )
    assert backend.calls == 1

    # A third adapter proves both process restart durability and terminal immutability.
    assert get_operation(SQLiteOperationStore(path), backend, operation.id) == reconciled
    assert backend.calls == 1


def test_duplicate_is_typed_and_does_not_replace_existing_mapping(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    migrate_database(path)
    operation = _operation()
    store = SQLiteOperationStore(path)
    assert isinstance(store.create_running(operation, BackendOperationRef("task-17")), Ok)
    changed = Operation(
        operation.id, ResourceReference("snapshots", "different"), "DELETE_SNAPSHOT", Running()
    )
    assert isinstance(store.create_running(changed, BackendOperationRef("task-99")), Err)
    loaded = store.get(operation.id)
    assert isinstance(loaded, Ok)
    assert loaded.value.operation == operation
    assert loaded.value.backend_ref == BackendOperationRef("task-17")


def test_terminal_compare_and_set_never_overwrites_terminal_state(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    migrate_database(path)
    operation = _operation()
    store = SQLiteOperationStore(path)
    store.create_running(operation, BackendOperationRef("task-17"))
    succeeded = Operation(operation.id, operation.target, operation.action, Succeeded())
    failed = Operation(
        operation.id,
        operation.target,
        operation.action,
        Failed(OperationFailure(BACKEND_OPERATION_FAILURE_REASON)),
    )
    assert store.complete(succeeded) == Ok(succeeded)
    assert store.complete(failed) == Ok(succeeded)


def test_unknown_uuid4_and_sqlite_failures_are_typed(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    migrate_database(path)
    unknown = OperationId(uuid7())
    assert SQLiteOperationStore(path).get(unknown) == Err(OperationNotFound(unknown))
    uuid4_id = OperationId(uuid4())
    with connect_database(path) as connection:
        connection.execute(
            """INSERT INTO operation VALUES (?, 'virtualMachines', 'vm', 'START',
            'RUNNING', NULL, 'task-bad')""",
            (str(uuid4_id),),
        )
        connection.commit()
    invalid_version = SQLiteOperationStore(path).get(uuid4_id)
    assert isinstance(invalid_version, Err)
    assert isinstance(invalid_version.error, OperationPersistenceFailure)
    broken = tmp_path / "missing" / "db.sqlite"
    failure = SQLiteOperationStore(broken).create_running(_operation(), BackendOperationRef("task"))
    assert isinstance(failure, Err) and isinstance(failure.error, OperationPersistenceFailure)
