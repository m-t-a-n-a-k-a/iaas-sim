# ruff: noqa: PLR2004
# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import uuid4, uuid7

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.snapshot import create_snapshot_router
from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.identity import BackendVirtualMachineRef
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.snapshot import ObservedSnapshot, SnapshotBackendFailure, SnapshotNotFound
from iaas_sim.domain.entity.snapshot import SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Err, Ok, Result

VM_ID = VirtualMachineId(uuid7())
REF = BackendVirtualMachineRef("vm-1")


class Identity:
    def get_or_create_by_backend_ref(self, backend_ref):
        return Ok(VM_ID)

    def get_backend_ref(self, virtual_machine_id):
        return Ok(REF)


class Port:
    def __init__(self):
        self.snapshot = ObservedSnapshot(SnapshotId("snapshot-1"), "before", REF)
        self.created = []

    def list_snapshots(self) -> Result[Sequence[ObservedSnapshot], SnapshotBackendFailure]:
        return Ok((self.snapshot,))

    def get_snapshot(self, snapshot_id):
        return (
            Ok(self.snapshot)
            if snapshot_id == self.snapshot.id
            else Err(SnapshotNotFound(snapshot_id))
        )

    def submit_create_snapshot(self, backend_ref, name):
        self.created.append((backend_ref, name))
        return Ok(BackendOperationRef("task-create"))

    def submit_delete_snapshot(self, snapshot_id):
        return Ok(BackendOperationRef("task-delete"))


def client():
    app = FastAPI()
    app.include_router(create_snapshot_router(Port(), Identity(), InMemoryOperationRegistry()))
    return TestClient(app)


def test_snapshot_owner_and_create_use_public_uuid():
    api = client()
    assert api.get("/v1/snapshots").json()["items"][0]["virtualMachine"]["id"] == str(VM_ID)
    response = api.post(
        "/v1/snapshots",
        json={
            "name": "new",
            "virtualMachine": {"resourceType": "virtualMachines", "id": str(VM_ID)},
        },
    )
    assert response.status_code == 202
    assert response.json()["target"]["id"] == str(VM_ID)


def test_create_rejects_mor_and_uuid4():

    api = client()
    for value in ("vm-1", str(uuid4())):
        assert (
            api.post(
                "/v1/snapshots",
                json={
                    "name": "x",
                    "virtualMachine": {"resourceType": "virtualMachines", "id": value},
                },
            ).status_code
            == 422
        )
