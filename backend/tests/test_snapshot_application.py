# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import uuid7

from iaas_sim.adapters.memory.operation import InMemoryOperationStore
from iaas_sim.application.identity import (
    BackendSnapshotRef,
    BackendVirtualMachineRef,
    SnapshotIdentityMapping,
)
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.snapshot import (
    BackendSnapshotNotFound,
    ObservedSnapshot,
    SnapshotBackendFailure,
    SnapshotBackendSubmissionFailure,
    SnapshotCommandSubmissionFailure,
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
        self.deleted = []

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
        self.deleted.append(snapshot_id)
        return Ok(BackendOperationRef("task-delete"))


def test_snapshot_projection_uses_public_vm_id():
    port = Port()
    identity = Identity()
    assert list_snapshots(port, identity, identity).value[0].virtual_machine.resource_id == str(
        VM_ID
    )
    assert get_snapshot(port, identity, identity, SNAPSHOT_ID).value.id == SNAPSHOT_ID


def test_create_resolves_backend_ref():
    port = Port()
    result = create_snapshot(
        port, Identity(), InMemoryOperationStore(), OperationId(uuid7()), VM_ID, "before"
    )
    assert isinstance(result, Ok)
    assert port.created == [(REF, "before")]
    assert result.value.target.resource_id == str(VM_ID)


def test_create_failure_maps_to_public_vm_identity():
    port = Port()
    port.submit_create_snapshot = lambda backend_ref, name: Err(
        SnapshotBackendSubmissionFailure("create", str(backend_ref), "failure for vm-1")
    )
    result = create_snapshot(
        port, Identity(), InMemoryOperationStore(), OperationId(uuid7()), VM_ID, "before"
    )
    assert result == Err(SnapshotCommandSubmissionFailure("create", str(VM_ID), "failure for vm-1"))
    assert result.error.resource_id == str(VM_ID)


def test_delete_keeps_snapshot_identity():
    port = Port()
    result = delete_snapshot(
        port, Identity(), InMemoryOperationStore(), OperationId(uuid7()), SNAPSHOT_ID
    )
    assert isinstance(result, Ok)
    assert port.deleted == [SNAPSHOT_REF]
