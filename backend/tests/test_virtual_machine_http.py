# ruff: noqa: PLR2004
# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import UUID, uuid4, uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.virtual_machine import (
    create_operation_router,
    create_virtual_machine_router,
)
from iaas_sim.adapters.memory.operation import InMemoryOperationStore
from iaas_sim.application.identity import (
    BackendVirtualMachineRef,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
)
from iaas_sim.application.operation import (
    BackendOperationFailed,
    BackendOperationRef,
    BackendOperationRunning,
    BackendOperationStatus,
    OperationPollingFailure,
)
from iaas_sim.application.virtual_machine import (
    ObservedVirtualMachine,
    PowerCommandBackendSubmissionFailure,
    VirtualMachineBackendFailure,
    VirtualMachineBackendNotFound,
)
from iaas_sim.domain.entity.virtual_machine import PowerCommand, PowerState, VirtualMachineId
from iaas_sim.result import Err, Ok, Result

VM_ID = VirtualMachineId(uuid7())
REF = BackendVirtualMachineRef("vm-1")


class Identity:
    def get_or_create_by_backend_ref(self, backend_ref):
        return Ok(VM_ID)

    def get_backend_ref(self, virtual_machine_id):
        return (
            Ok(REF)
            if virtual_machine_id == VM_ID
            else Err(VirtualMachineIdentityNotFound(virtual_machine_id))
        )


class Port:
    def __init__(self):
        self.vm = ObservedVirtualMachine(REF, "demo", PowerState.STOPPED)
        self.backend_status: BackendOperationStatus = BackendOperationRunning()
        self.polled = []
        self.submitted = []

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[ObservedVirtualMachine], VirtualMachineBackendFailure]:
        return Ok((self.vm,))

    def get_virtual_machine(self, backend_ref):
        if backend_ref == REF:
            return Ok(self.vm)
        return Err(VirtualMachineBackendNotFound(backend_ref))

    def submit_power_command(self, backend_ref, command):
        self.submitted.append((backend_ref, command))
        return Ok(BackendOperationRef("task-1"))

    def get_operation_status(self, backend_ref):
        self.polled.append(backend_ref)
        return Ok(self.backend_status)


def client_for(port):
    registry = InMemoryOperationStore()
    app = FastAPI()
    app.include_router(create_virtual_machine_router(port, Identity(), registry))
    app.include_router(create_operation_router(registry, port))
    return TestClient(app)


def test_list_get_and_start_use_uuid7():
    port = Port()
    client = client_for(port)
    listed = client.get("/v1/virtualMachines").json()["items"][0]
    assert UUID(listed["id"]).version == 7
    assert listed["id"] == str(VM_ID)
    assert client.get(f"/v1/virtualMachines/{VM_ID}").status_code == 200
    response = client.post(f"/v1/virtualMachines/{VM_ID}:start")
    assert response.status_code == 202
    assert response.json()["target"]["id"] == str(VM_ID)
    assert port.submitted == [(REF, PowerCommand.START)]


@pytest.mark.parametrize("invalid", ["vm-1", str(uuid4())])
def test_paths_reject_non_uuid7(invalid):
    client = client_for(Port())
    assert client.get(f"/v1/virtualMachines/{invalid}").status_code == 422
    assert client.post(f"/v1/virtualMachines/{invalid}:start").status_code == 422
    assert client.post(f"/v1/virtualMachines/{invalid}:stop").status_code == 422


def test_validation_error_does_not_submit():
    port = Port()
    port.vm = ObservedVirtualMachine(REF, "demo", PowerState.RUNNING)
    assert client_for(port).post(f"/v1/virtualMachines/{VM_ID}:start").status_code == 409
    assert port.submitted == []


def test_power_submission_failure_does_not_expose_backend_identity():
    port = Port()
    port.submit_power_command = lambda backend_ref, command: Err(
        PowerCommandBackendSubmissionFailure(backend_ref, "failure for vm-1")
    )
    response = client_for(port).post(f"/v1/virtualMachines/{VM_ID}:start")
    assert response.status_code == 502
    assert response.json() == {"detail": "VirtualMachine power command submission failed"}
    assert "vm-1" not in response.text


def test_backend_not_found_does_not_expose_backend_identity():
    port = Port()
    port.get_virtual_machine = lambda backend_ref: Err(VirtualMachineBackendNotFound(backend_ref))
    response = client_for(port).get(f"/v1/virtualMachines/{VM_ID}")
    assert response.status_code == 404
    assert response.json() == {"detail": "VirtualMachine not found"}
    assert "vm-1" not in response.text


def test_backend_failure_does_not_expose_backend_reason():
    port = Port()
    port.list_virtual_machines = lambda: Err(VirtualMachineBackendFailure("list", "vm-123"))
    response = client_for(port).get("/v1/virtualMachines")
    assert response.status_code == 502
    assert response.json() == {"detail": "VirtualMachine backend request failed"}
    assert "vm-123" not in response.text


def test_identity_persistence_failure_does_not_expose_backend_reason():
    class FailingIdentity(Identity):
        def get_or_create_by_backend_ref(self, backend_ref):
            return Err(
                VirtualMachineIdentityPersistenceFailure(
                    "get-or-create", "database failed for vm-123"
                )
            )

    app = FastAPI()
    app.include_router(
        create_virtual_machine_router(Port(), FailingIdentity(), InMemoryOperationStore())
    )
    response = TestClient(app).get("/v1/virtualMachines")
    assert response.status_code == 500
    assert response.json() == {"detail": "VirtualMachine internal error"}
    assert "vm-123" not in response.text


def test_operation_polling_failure_does_not_expose_backend_reason():
    port = Port()
    api = client_for(port)
    accepted = api.post(f"/v1/virtualMachines/{VM_ID}:start")
    operation_path = accepted.headers["location"]
    port.get_operation_status = lambda backend_ref: Err(OperationPollingFailure("task-17"))

    response = api.get(operation_path)

    assert response.status_code == 502
    assert response.json() == {"detail": "Operation polling failed"}
    assert "task-17" not in response.text


def test_failed_operation_resource_uses_public_safe_reason():
    port = Port()
    api = client_for(port)
    accepted = api.post(f"/v1/virtualMachines/{VM_ID}:start")
    operation_path = accepted.headers["location"]
    raw_reason = "task-17 vm-123 internal backend failure"
    port.backend_status = BackendOperationFailed(raw_reason)
    response = api.get(operation_path)

    assert response.status_code == 200
    assert response.json()["failure"] == {"reason": "Backend operation failed"}
    assert raw_reason not in response.text
