from collections.abc import Sequence
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.virtual_machine import (
    create_operation_router,
    create_virtual_machine_router,
)
from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRef,
    BackendOperationRunning,
    BackendOperationStatus,
    BackendOperationSucceeded,
    OperationPollingFailure,
)
from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
)
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

STATUS_OK = 200
STATUS_ACCEPTED = 202
STATUS_NOT_FOUND = 404
STATUS_CONFLICT = 409
UUID_VERSION_7 = 7


class FakePort:
    def __init__(self) -> None:
        self.vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.STOPPED)
        self.backend_status: BackendOperationStatus = BackendOperationRunning()
        self.polled: list[BackendOperationRef] = []

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]:
        return Ok((self.vm,))

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[VirtualMachine, VirtualMachineNotFound | VirtualMachineAdapterFailure]:
        return (
            Ok(self.vm)
            if virtual_machine_id == self.vm.id
            else Err(VirtualMachineNotFound(virtual_machine_id))
        )

    def submit_power_command(
        self, virtual_machine_id: VirtualMachineId, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandSubmissionFailure]:
        return Ok(BackendOperationRef("task-mock-mor"))

    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]:
        self.polled.append(backend_ref)
        return Ok(self.backend_status)


def client_for(port: FakePort) -> TestClient:
    registry = InMemoryOperationRegistry()
    app = FastAPI()
    app.include_router(create_virtual_machine_router(port, registry))
    app.include_router(create_operation_router(registry, port))
    return TestClient(app)


@pytest.mark.parametrize(
    ("backend_status", "state", "failure"),
    [
        pytest.param(BackendOperationRunning(), "RUNNING", None, id="running"),
        pytest.param(BackendOperationSucceeded(), "SUCCEEDED", None, id="succeeded"),
        pytest.param(BackendOperationFailed("boom"), "FAILED", {"reason": "boom"}, id="failed"),
    ],
)
def test_post_then_get_tracks_current_backend_status(
    backend_status: BackendOperationStatus, state: str, failure: object
) -> None:
    port = FakePort()
    client = client_for(port)
    submitted = client.post("/v1/virtualMachines/vm-1:start")
    assert submitted.status_code == STATUS_ACCEPTED
    operation_id = UUID(submitted.json()["id"])
    assert operation_id.version == UUID_VERSION_7
    assert submitted.json()["target"] == {"resourceType": "virtualMachines", "id": "vm-1"}

    port.backend_status = backend_status
    response = client.get(submitted.headers["Location"])
    assert response.status_code == STATUS_OK
    assert response.json()["state"] == state
    assert response.json()["failure"] == failure
    assert port.polled == [BackendOperationRef("task-mock-mor")]


def test_unknown_operation_returns_404_without_polling() -> None:
    port = FakePort()
    response = client_for(port).get("/v1/operations/0198f5d0-7300-7000-8000-000000000000")
    assert response.status_code == STATUS_NOT_FOUND
    assert port.polled == []


def test_validation_error_does_not_submit() -> None:
    port = FakePort()
    port.vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.RUNNING)
    assert client_for(port).post("/v1/virtualMachines/vm-1:start").status_code == STATUS_CONFLICT
