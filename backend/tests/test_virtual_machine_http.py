from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.virtual_machine import (
    create_operation_router,
    create_virtual_machine_router,
)
from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
)
from iaas_sim.domain.entity.operation import VsphereTaskRef
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

# HTTP status codes
STATUS_OK = 200
STATUS_ACCEPTED = 202
STATUS_CONFLICT = 409
STATUS_NOT_IMPLEMENTED = 501


class FakePort:
    """Test port for HTTP layer: simulates async power submission."""

    def __init__(self) -> None:
        self.vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.STOPPED)

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
    ) -> Result[VsphereTaskRef, PowerCommandSubmissionFailure]:
        # Simulate successful async submission (doesn't mutate VM state)
        return Ok(VsphereTaskRef("task-mock-mor"))


def test_virtual_machine_routes() -> None:
    """Test basic GET endpoints (unchanged behavior)."""
    app = FastAPI()
    app.include_router(create_virtual_machine_router(FakePort()))
    app.include_router(create_operation_router())
    client = TestClient(app)

    # GET list
    assert client.get("/v1/virtualMachines").status_code == STATUS_OK
    assert client.get("/v1/virtualMachines").json() == {
        "items": [{"id": "vm-1", "name": "demo", "powerState": "STOPPED"}]
    }

    # GET single
    assert client.get("/v1/virtualMachines/vm-1").status_code == STATUS_OK


def test_power_command_returns_202_accepted() -> None:
    """Test async power command: 202 Accepted with Location header."""
    app = FastAPI()
    app.include_router(create_virtual_machine_router(FakePort()))
    app.include_router(create_operation_router())
    client = TestClient(app)

    # POST :start
    response = client.post("/v1/virtualMachines/vm-1:start")
    assert response.status_code == STATUS_ACCEPTED

    # Verify Location header
    assert "Location" in response.headers
    assert response.headers["Location"].startswith("/v1/operations/")

    # Verify response body contains Operation
    body = response.json()
    assert body["action"] == "START"
    assert body["state"] == "RUNNING"
    assert body["targetVirtualMachineId"] == "vm-1"
    assert body["failure"] is None


def test_power_command_start_on_running_vm_rejected() -> None:
    """Test validation error: 409 Conflict."""
    port = FakePort()
    port.vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.RUNNING)

    app = FastAPI()
    app.include_router(create_virtual_machine_router(port))
    app.include_router(create_operation_router())
    client = TestClient(app)

    response = client.post("/v1/virtualMachines/vm-1:start")
    assert response.status_code == STATUS_CONFLICT


def test_operation_get_not_implemented() -> None:
    """Test GET /operations/{id}: Phase 2A returns 501 Not Implemented."""
    app = FastAPI()
    app.include_router(create_operation_router())
    client = TestClient(app)

    response = client.get("/v1/operations/some-id")
    assert response.status_code == STATUS_NOT_IMPLEMENTED
