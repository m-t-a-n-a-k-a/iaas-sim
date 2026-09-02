from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.snapshot import create_snapshot_router
from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.snapshot import (
    SnapshotBackendFailure,
    SnapshotCommandSubmissionFailure,
    SnapshotNotFound,
)
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result

STATUS_ACCEPTED = 202
STATUS_NOT_FOUND = 404
STATUS_UNPROCESSABLE = 422


class Port:
    def __init__(self) -> None:
        self.snapshot = Snapshot(
            SnapshotId("snapshot-1"), "before", ResourceReference("virtualMachines", "vm-1")
        )

    def list_snapshots(self) -> Result[Sequence[Snapshot], SnapshotBackendFailure]:
        return Ok((self.snapshot,))

    def get_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[Snapshot, SnapshotNotFound | SnapshotBackendFailure]:
        return (
            Ok(self.snapshot)
            if snapshot_id == self.snapshot.id
            else Err(SnapshotNotFound(snapshot_id))
        )

    def submit_create_snapshot(
        self, virtual_machine_id: VirtualMachineId, name: str
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]:
        return Ok(BackendOperationRef("create"))

    def submit_delete_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]:
        return Ok(BackendOperationRef("delete"))


def client() -> TestClient:
    app = FastAPI()
    app.include_router(create_snapshot_router(Port(), InMemoryOperationRegistry()))
    return TestClient(app)


def test_snapshot_crud_routes_are_flat_and_serialize_reference() -> None:
    api = client()
    expected = {
        "id": "snapshot-1",
        "name": "before",
        "virtualMachine": {"resourceType": "virtualMachines", "id": "vm-1"},
    }
    assert api.get("/v1/snapshots").json() == {"items": [expected]}
    assert api.get("/v1/snapshots/snapshot-1").json() == expected
    assert api.get("/v1/snapshots/unknown").status_code == STATUS_NOT_FOUND
    created = api.post(
        "/v1/snapshots",
        json={"name": "new", "virtualMachine": {"resourceType": "virtualMachines", "id": "vm-1"}},
    )
    assert created.status_code == STATUS_ACCEPTED and created.headers["location"].startswith(
        "/v1/operations/"
    )
    assert created.json()["target"] == {"resourceType": "virtualMachines", "id": "vm-1"}
    deleted = api.delete("/v1/snapshots/snapshot-1")
    assert deleted.status_code == STATUS_ACCEPTED and deleted.json()["target"] == {
        "resourceType": "snapshots",
        "id": "snapshot-1",
    }


def test_create_rejects_non_vm_reference() -> None:
    response = client().post(
        "/v1/snapshots",
        json={"name": "x", "virtualMachine": {"resourceType": "snapshots", "id": "vm-1"}},
    )
    assert response.status_code == STATUS_UNPROCESSABLE
