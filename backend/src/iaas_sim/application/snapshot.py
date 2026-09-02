from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationRegistryPort,
    TrackedOperation,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, Running
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Ok, Result, and_then, map


@dataclass(frozen=True, slots=True)
class SnapshotNotFound:
    snapshot_id: SnapshotId


@dataclass(frozen=True, slots=True)
class SnapshotBackendFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class SnapshotCommandSubmissionFailure:
    operation: str
    resource_id: str
    reason: str


type SnapshotApplicationError = (
    SnapshotNotFound | SnapshotBackendFailure | SnapshotCommandSubmissionFailure
)


class SnapshotPort(Protocol):
    def list_snapshots(self) -> Result[Sequence[Snapshot], SnapshotBackendFailure]: ...
    def get_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[Snapshot, SnapshotNotFound | SnapshotBackendFailure]: ...
    def submit_create_snapshot(
        self, virtual_machine_id: VirtualMachineId, name: str
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]: ...
    def submit_delete_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[BackendOperationRef, SnapshotCommandSubmissionFailure]: ...


def list_snapshots(port: SnapshotPort) -> Result[Sequence[Snapshot], SnapshotBackendFailure]:
    return port.list_snapshots()


def get_snapshot(
    port: SnapshotPort, snapshot_id: SnapshotId
) -> Result[Snapshot, SnapshotNotFound | SnapshotBackendFailure]:
    return port.get_snapshot(snapshot_id)


def _register(
    registry: OperationRegistryPort, tracked: TrackedOperation
) -> Result[Operation, SnapshotApplicationError]:
    registry.add(tracked)
    return Ok(Operation(tracked.id, tracked.target, tracked.action, Running()))


def create_snapshot(
    port: SnapshotPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    name: str,
) -> Result[Operation, SnapshotApplicationError]:
    tracked = map(
        port.submit_create_snapshot(virtual_machine_id, name),
        lambda backend_ref: TrackedOperation(
            operation_id,
            ResourceReference("virtualMachines", str(virtual_machine_id)),
            "CREATE_SNAPSHOT",
            backend_ref,
        ),
    )
    return and_then(tracked, lambda operation: _register(registry, operation))


def delete_snapshot(
    port: SnapshotPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    snapshot_id: SnapshotId,
) -> Result[Operation, SnapshotApplicationError]:
    submitted = and_then(
        port.get_snapshot(snapshot_id), lambda snapshot: port.submit_delete_snapshot(snapshot.id)
    )
    tracked = map(
        submitted,
        lambda backend_ref: TrackedOperation(
            operation_id,
            ResourceReference("snapshots", str(snapshot_id)),
            "DELETE_SNAPSHOT",
            backend_ref,
        ),
    )
    return and_then(tracked, lambda operation: _register(registry, operation))
