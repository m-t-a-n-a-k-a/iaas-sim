# ruff: noqa: PLR2004
# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import uuid4, uuid7

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.snapshot import create_snapshot_router
from iaas_sim.adapters.memory.operation import InMemoryOperationStore
from iaas_sim.application.identity import (
    BackendSnapshotRef,
    BackendVirtualMachineRef,
    SnapshotIdentityMapping,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
)
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.snapshot import (
    BackendSnapshotNotFound,
    ObservedSnapshot,
    SnapshotBackendFailure,
    SnapshotBackendSubmissionFailure,
)
from iaas_sim.domain.entity.snapshot import SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Err, Ok, Result

VM_ID = VirtualMachineId(uuid7())
SNAPSHOT_ID = SnapshotId(uuid7())
SNAPSHOT_REF = BackendSnapshotRef("snapshot-1")
REF = BackendVirtualMachineRef("vm-1")


class Identity:
    def get_or_create_by_backend_ref(self, backend_ref):
        return Ok(VM_ID)

    def get_backend_ref(self, virtual_machine_id):
        return Ok(REF)

    def get_or_create_snapshot(self, backend_ref, virtual_machine_id):
        return Ok(SNAPSHOT_ID)

    def get_snapshot_mapping(self, snapshot_id):
        return Ok(SnapshotIdentityMapping(SNAPSHOT_REF, VM_ID))


class Port:
    def __init__(self):
        self.snapshot = ObservedSnapshot(SNAPSHOT_REF, "before", REF)
        self.created = []

    def list_snapshots(self) -> Result[Sequence[ObservedSnapshot], SnapshotBackendFailure]:
        return Ok((self.snapshot,))

    def get_snapshot(self, snapshot_id):
        return (
            Ok(self.snapshot)
            if snapshot_id == self.snapshot.backend_ref
            else Err(BackendSnapshotNotFound(snapshot_id))
        )

    def submit_create_snapshot(self, backend_ref, name):
        self.created.append((backend_ref, name))
        return Ok(BackendOperationRef("task-create"))

    def submit_delete_snapshot(self, snapshot_id):
        return Ok(BackendOperationRef("task-delete"))


def client(port=None):
    app = FastAPI()
    app.include_router(
        create_snapshot_router(port or Port(), Identity(), Identity(), InMemoryOperationStore())
    )
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


def test_create_failure_does_not_expose_backend_identity():
    port = Port()
    port.submit_create_snapshot = lambda backend_ref, name: Err(
        SnapshotBackendSubmissionFailure("create", str(backend_ref), "failure for vm-1")
    )
    response = client(port).post(
        "/v1/snapshots",
        json={
            "name": "new",
            "virtualMachine": {"resourceType": "virtualMachines", "id": str(VM_ID)},
        },
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "Snapshot creation submission failed"}
    assert "vm-1" not in response.text


def test_backend_failure_does_not_expose_backend_reason():
    port = Port()
    port.list_snapshots = lambda: Err(
        SnapshotBackendFailure("list", "snapshot-42 belongs to vm-123")
    )
    response = client(port).get("/v1/snapshots")
    assert response.status_code == 502
    assert response.json() == {"detail": "Snapshot backend request failed"}
    assert "snapshot-42" not in response.text
    assert "vm-123" not in response.text


def test_identity_persistence_failure_does_not_expose_backend_reason():
    class FailingIdentity(Identity):
        def get_or_create_by_backend_ref(self, backend_ref):
            return Err(
                VirtualMachineIdentityPersistenceFailure(
                    "get-or-create", "database failed for snapshot-42 vm-123"
                )
            )

    app = FastAPI()
    app.include_router(
        create_snapshot_router(
            Port(), FailingIdentity(), FailingIdentity(), InMemoryOperationStore()
        )
    )
    response = TestClient(app).get("/v1/snapshots")
    assert response.status_code == 500
    assert response.json() == {"detail": "Snapshot internal error"}
    assert "snapshot-42" not in response.text
    assert "vm-123" not in response.text


def test_identity_not_found_uses_stable_public_message():
    class MissingIdentity(Identity):
        def get_backend_ref(self, virtual_machine_id):
            return Err(VirtualMachineIdentityNotFound(virtual_machine_id))

    app = FastAPI()
    app.include_router(
        create_snapshot_router(
            Port(), MissingIdentity(), MissingIdentity(), InMemoryOperationStore()
        )
    )
    response = TestClient(app).post(
        "/v1/snapshots",
        json={
            "name": "new",
            "virtualMachine": {"resourceType": "virtualMachines", "id": str(VM_ID)},
        },
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "VirtualMachine not found"}


def test_snapshot_item_paths_require_uuid7_and_never_expose_mor():
    api = client()
    listed = api.get("/v1/snapshots")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["id"] == str(SNAPSHOT_ID)
    assert item["virtualMachine"]["id"] == str(VM_ID)
    assert "snapshot-1" not in listed.text
    assert api.get(f"/v1/snapshots/{SNAPSHOT_ID}").status_code == 200
    deleted = api.delete(f"/v1/snapshots/{SNAPSHOT_ID}")
    assert deleted.status_code == 202
    assert deleted.json()["target"]["id"] == str(SNAPSHOT_ID)
    for invalid in ("snapshot-42", "not-a-uuid", str(uuid4())):
        assert api.get(f"/v1/snapshots/{invalid}").status_code == 422
        assert api.delete(f"/v1/snapshots/{invalid}").status_code == 422
