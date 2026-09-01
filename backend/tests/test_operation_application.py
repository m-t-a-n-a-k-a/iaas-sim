from uuid import uuid7

import pytest

from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.get_operation import get_operation
from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRef,
    BackendOperationRunning,
    BackendOperationStatus,
    BackendOperationSucceeded,
    OperationNotFound,
    OperationPollingFailure,
    TrackedOperation,
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
    def __init__(self, status: BackendOperationStatus) -> None:
        self.status = status

    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]:
        assert backend_ref == BackendOperationRef("opaque-ref")
        return Ok(self.status)


@pytest.mark.parametrize(
    ("backend_status", "expected_status"),
    [
        pytest.param(BackendOperationRunning(), Running(), id="running"),
        pytest.param(BackendOperationSucceeded(), Succeeded(), id="succeeded"),
        pytest.param(
            BackendOperationFailed("boom"),
            Failed(OperationFailure("boom")),
            id="failed-with-required-error",
        ),
    ],
)
def test_backend_status_is_projected_to_operation_adt(
    backend_status: BackendOperationStatus, expected_status: OperationStatus
) -> None:
    operation_id = OperationId(uuid7())
    target = ResourceReference("virtualMachines", "vm-1")
    registry = InMemoryOperationRegistry()
    registry.add(TrackedOperation(operation_id, target, "START", BackendOperationRef("opaque-ref")))

    assert get_operation(registry, FakeBackend(backend_status), operation_id) == Ok(
        Operation(operation_id, target, "START", expected_status)
    )


def test_unknown_operation_is_typed_failure() -> None:
    operation_id = OperationId(uuid7())
    assert get_operation(
        InMemoryOperationRegistry(), FakeBackend(BackendOperationRunning()), operation_id
    ) == Err(OperationNotFound(operation_id))


def test_operation_status_constructors_only_allow_valid_shapes() -> None:
    assert Running() == Running()
    assert Succeeded() == Succeeded()
    assert Failed(OperationFailure("required")) == Failed(OperationFailure("required"))
