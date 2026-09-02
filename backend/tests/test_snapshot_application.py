from collections.abc import Sequence
from uuid import UUID

from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.snapshot import (
    SnapshotBackendFailure,
    SnapshotCommandSubmissionFailure,
    SnapshotNotFound,
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
)
from iaas_sim.domain.entity.operation import OperationId, Running
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result

OPERATION_ID = OperationId(UUID("0198f5d0-7300-7000-8000-000000000000"))


class FakeSnapshotPort:
    def __init__(self) -> None:
        self.snapshot = Snapshot(
            SnapshotId("snapshot-1"), "before-upgrade", ResourceReference("virtualMachines", "vm-1")
        )
        self.backend_failure: SnapshotBackendFailure | None = None
        self.submission_failure: SnapshotCommandSubmissionFailure | None = None
        self.created: list[tuple[VirtualMachineId, str]] = []
        self.deleted: list[SnapshotId] = []

    def list_snapshots(self) -> Result[Sequence[Snapshot], SnapshotBackendFailure]:
        return Err(self.backend_failure) if self.backend_failure else Ok((self.snapshot,))

    def get_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[Snapshot, SnapshotNotFound | SnapshotBackendFailure]:
        if self.backend_failure:
            return Err(self.backend_failure)
        return (
            Ok(self.snapshot)
            if snapshot_id == self.snapshot.id
            else Err(SnapshotNotFound(snapshot_id))
        )

    def submit_create_snapshot(
        self, virtual_machine_id: VirtualMachineId, name: str
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]:
        self.created.append((virtual_machine_id, name))
        return (
            Err(self.submission_failure)
            if self.submission_failure
            else Ok(BackendOperationRef("task-create"))
        )

    def submit_delete_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]:
        self.deleted.append(snapshot_id)
        return (
            Err(self.submission_failure)
            if self.submission_failure
            else Ok(BackendOperationRef("task-delete"))
        )


def test_snapshot_reads_and_failures_propagate() -> None:
    port = FakeSnapshotPort()
    assert isinstance(list_snapshots(port), Ok)
    assert get_snapshot(port, port.snapshot.id) == Ok(port.snapshot)
    assert get_snapshot(port, SnapshotId("unknown")) == Err(SnapshotNotFound(SnapshotId("unknown")))
    port.backend_failure = SnapshotBackendFailure("list", "offline")
    assert list_snapshots(port) == Err(port.backend_failure)


def test_create_registers_vm_target_only_after_submission() -> None:
    port, registry = FakeSnapshotPort(), InMemoryOperationRegistry()
    result = create_snapshot(
        port, registry, OPERATION_ID, VirtualMachineId("vm-1"), "before-upgrade"
    )
    assert isinstance(result, Ok) and isinstance(result.value.status, Running)
    assert result.value.target == ResourceReference("virtualMachines", "vm-1")
    assert registry.get(OPERATION_ID) is not None
    port.submission_failure = SnapshotCommandSubmissionFailure("create", "vm-1", "no")
    other = OperationId(UUID("0198f5d0-7300-7000-8000-000000000001"))
    assert isinstance(create_snapshot(port, registry, other, VirtualMachineId("vm-1"), "x"), Err)
    assert registry.get(other) is None


def test_delete_short_circuits_and_registers_snapshot_target() -> None:
    port, registry = FakeSnapshotPort(), InMemoryOperationRegistry()
    result = delete_snapshot(port, registry, OPERATION_ID, port.snapshot.id)
    assert isinstance(result, Ok) and result.value.target == ResourceReference(
        "snapshots", "snapshot-1"
    )
    assert port.deleted == [port.snapshot.id]
    port.deleted.clear()
    other = OperationId(UUID("0198f5d0-7300-7000-8000-000000000001"))
    assert isinstance(delete_snapshot(port, registry, other, SnapshotId("unknown")), Err)
    assert port.deleted == [] and registry.get(other) is None
    port.submission_failure = SnapshotCommandSubmissionFailure("delete", "snapshot-1", "no")
    assert isinstance(delete_snapshot(port, registry, other, port.snapshot.id), Err)
    assert registry.get(other) is None
