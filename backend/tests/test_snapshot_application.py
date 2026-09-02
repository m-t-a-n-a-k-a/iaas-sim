# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import uuid7

from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.identity import BackendVirtualMachineRef
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.snapshot import (
    ObservedSnapshot,
    SnapshotBackendFailure,
    SnapshotNotFound,
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
)
from iaas_sim.domain.entity.operation import OperationId
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
        self.deleted = []

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
        self.deleted.append(snapshot_id)
        return Ok(BackendOperationRef("task-delete"))


def test_snapshot_projection_uses_public_vm_id():
    port = Port()
    identity = Identity()
    assert list_snapshots(port, identity).value[0].virtual_machine.resource_id == str(VM_ID)
    assert get_snapshot(port, identity, port.snapshot.id).value.id == port.snapshot.id


def test_create_resolves_backend_ref():
    port = Port()
    result = create_snapshot(
        port, Identity(), InMemoryOperationRegistry(), OperationId(uuid7()), VM_ID, "before"
    )
    assert isinstance(result, Ok)
    assert port.created == [(REF, "before")]
    assert result.value.target.resource_id == str(VM_ID)


def test_delete_keeps_snapshot_identity():
    port = Port()
    result = delete_snapshot(
        port, Identity(), InMemoryOperationRegistry(), OperationId(uuid7()), port.snapshot.id
    )
    assert isinstance(result, Ok)
    assert port.deleted == [SnapshotId("snapshot-1")]
