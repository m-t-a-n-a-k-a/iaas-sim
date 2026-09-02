from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.identity import (
    BackendVirtualMachineRef,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
    VirtualMachineIdentityPort,
)
from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationRegistryPort,
    TrackedOperation,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, Running
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class ObservedSnapshot:
    id: SnapshotId
    name: str
    owner_backend_ref: BackendVirtualMachineRef


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


@dataclass(frozen=True, slots=True)
class SnapshotBackendSubmissionFailure:
    operation: str
    resource_id: str
    reason: str


type SnapshotApplicationError = (
    SnapshotNotFound
    | SnapshotBackendFailure
    | SnapshotCommandSubmissionFailure
    | VirtualMachineIdentityPersistenceFailure
    | VirtualMachineIdentityNotFound
)


class SnapshotPort(Protocol):
    def list_snapshots(self) -> Result[Sequence[ObservedSnapshot], SnapshotBackendFailure]: ...
    def get_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[ObservedSnapshot, SnapshotNotFound | SnapshotBackendFailure]: ...
    def submit_create_snapshot(
        self, backend_ref: BackendVirtualMachineRef, name: str
    ) -> Result[BackendOperationRef, SnapshotBackendSubmissionFailure]: ...
    def submit_delete_snapshot(
        self, snapshot_id: SnapshotId
    ) -> Result[BackendOperationRef, SnapshotBackendSubmissionFailure]: ...


def _project(
    observed: ObservedSnapshot, identity: VirtualMachineIdentityPort
) -> Result[Snapshot, SnapshotApplicationError]:
    owner = identity.get_or_create_by_backend_ref(observed.owner_backend_ref)
    if isinstance(owner, Err):
        return Err(owner.error)
    return Ok(
        Snapshot(observed.id, observed.name, ResourceReference("virtualMachines", str(owner.value)))
    )


def list_snapshots(
    port: SnapshotPort, identity: VirtualMachineIdentityPort
) -> Result[Sequence[Snapshot], SnapshotApplicationError]:
    listed = port.list_snapshots()
    if isinstance(listed, Err):
        return Err(listed.error)
    values: list[Snapshot] = []
    for item in listed.value:
        projected = _project(item, identity)
        if isinstance(projected, Err):
            return projected
        values.append(projected.value)
    return Ok(tuple(values))


def get_snapshot(
    port: SnapshotPort, identity: VirtualMachineIdentityPort, snapshot_id: SnapshotId
) -> Result[Snapshot, SnapshotApplicationError]:
    observed = port.get_snapshot(snapshot_id)
    if isinstance(observed, Err):
        return Err(observed.error)
    return _project(observed.value, identity)


def _register(
    registry: OperationRegistryPort, tracked: TrackedOperation
) -> Result[Operation, SnapshotApplicationError]:
    registry.add(tracked)
    return Ok(Operation(tracked.id, tracked.target, tracked.action, Running()))


def create_snapshot(  # noqa: PLR0917
    port: SnapshotPort,
    identity: VirtualMachineIdentityPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    name: str,
) -> Result[Operation, SnapshotApplicationError]:
    mapped = identity.get_backend_ref(virtual_machine_id)
    if isinstance(mapped, Err):
        return Err(mapped.error)
    submitted = port.submit_create_snapshot(mapped.value, name)
    if isinstance(submitted, Err):
        return Err(
            SnapshotCommandSubmissionFailure(
                "create", str(virtual_machine_id), submitted.error.reason
            )
        )
    return _register(
        registry,
        TrackedOperation(
            operation_id,
            ResourceReference("virtualMachines", str(virtual_machine_id)),
            "CREATE_SNAPSHOT",
            submitted.value,
        ),
    )


def delete_snapshot(
    port: SnapshotPort,
    identity: VirtualMachineIdentityPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    snapshot_id: SnapshotId,
) -> Result[Operation, SnapshotApplicationError]:
    observed = port.get_snapshot(snapshot_id)
    if isinstance(observed, Err):
        return Err(observed.error)
    submitted = port.submit_delete_snapshot(snapshot_id)
    if isinstance(submitted, Err):
        return Err(
            SnapshotCommandSubmissionFailure("delete", str(snapshot_id), submitted.error.reason)
        )
    return _register(
        registry,
        TrackedOperation(
            operation_id,
            ResourceReference("snapshots", str(snapshot_id)),
            "DELETE_SNAPSHOT",
            submitted.value,
        ),
    )
