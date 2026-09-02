from uuid import uuid7

import pytest

from iaas_sim.adapters.memory.operation import InMemoryOperationStore
from iaas_sim.application.get_operation import BACKEND_OPERATION_FAILURE_REASON, get_operation
from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRef,
    BackendOperationRunning,
    BackendOperationStatus,
    BackendOperationSucceeded,
    OperationNotFound,
    OperationPollingFailure,
)
from iaas_sim.domain.entity.operation import (
    Failed,
    Operation,
    OperationFailure,
    OperationId,
    OperationStatus,
    ResourceReference,
    Running,
    Succeeded,
)
from iaas_sim.result import Err, Ok, Result


class FakeBackend:
    def __init__(self, status: BackendOperationStatus | OperationPollingFailure) -> None:
        self.status = status

    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]:
        assert backend_ref == BackendOperationRef("opaque-ref")
        if isinstance(self.status, OperationPollingFailure):
            return Err(self.status)
        return Ok(self.status)


@pytest.mark.parametrize(
    ("backend_status", "expected_status"),
    [
        pytest.param(BackendOperationRunning(), Running(), id="running"),
        pytest.param(BackendOperationSucceeded(), Succeeded(), id="succeeded"),
        pytest.param(
            BackendOperationFailed("task-17 vm-123 internal backend failure"),
            Failed(OperationFailure(BACKEND_OPERATION_FAILURE_REASON)),
            id="failed-with-required-error",
        ),
    ],
)
def test_backend_status_is_projected_to_operation_adt(
    backend_status: BackendOperationStatus, expected_status: OperationStatus
) -> None:
    operation_id = OperationId(uuid7())
    target = ResourceReference("virtualMachines", "vm-1")
    store = InMemoryOperationStore()
    assert store.create_running(
        Operation(operation_id, target, "START", Running()), BackendOperationRef("opaque-ref")
    ) == Ok(Operation(operation_id, target, "START", Running()))

    assert get_operation(store, FakeBackend(backend_status), operation_id) == Ok(
        Operation(operation_id, target, "START", expected_status)
    )


def test_unknown_operation_is_typed_failure() -> None:
    operation_id = OperationId(uuid7())
    assert get_operation(
        InMemoryOperationStore(), FakeBackend(BackendOperationRunning()), operation_id
    ) == Err(OperationNotFound(operation_id))


def test_polling_failure_is_returned_unchanged() -> None:
    operation_id = OperationId(uuid7())
    failure = OperationPollingFailure("backend unavailable")
    store = InMemoryOperationStore()
    store.create_running(
        Operation(operation_id, ResourceReference("virtualMachines", "vm-1"), "START", Running()),
        BackendOperationRef("opaque-ref"),
    )

    assert get_operation(store, FakeBackend(failure), operation_id) == Err(failure)


def test_operation_status_constructors_only_allow_valid_shapes() -> None:
    assert Running() == Running()
    assert Succeeded() == Succeeded()
    assert Failed(OperationFailure("required")) == Failed(OperationFailure("required"))
