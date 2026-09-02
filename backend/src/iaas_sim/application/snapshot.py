from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.identity import (
    BackendSnapshotRef,
    BackendVirtualMachineRef,
    SnapshotIdentityNotFound,
    SnapshotIdentityOwnerMismatch,
    SnapshotIdentityPersistenceFailure,
    SnapshotIdentityPort,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
    VirtualMachineIdentityPort,
)
from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationPersistenceFailure,
    OperationStorePort,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, Running
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class ObservedSnapshot:
    backend_ref: BackendSnapshotRef
    name: str
    owner_backend_ref: BackendVirtualMachineRef


@dataclass(frozen=True, slots=True)
class BackendSnapshotNotFound:
    backend_ref: BackendSnapshotRef


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
    | SnapshotIdentityPersistenceFailure
    | SnapshotIdentityOwnerMismatch
    | OperationPersistenceFailure
)


class SnapshotPort(Protocol):
    def list_snapshots(self) -> Result[Sequence[ObservedSnapshot], SnapshotBackendFailure]: ...
    def get_snapshot(
        self, backend_ref: BackendSnapshotRef
    ) -> Result[ObservedSnapshot, BackendSnapshotNotFound | SnapshotBackendFailure]: ...
    def submit_create_snapshot(
        self, backend_ref: BackendVirtualMachineRef, name: str
    ) -> Result[BackendOperationRef, SnapshotBackendSubmissionFailure]: ...
    def submit_delete_snapshot(
        self, backend_ref: BackendSnapshotRef
    ) -> Result[BackendOperationRef, SnapshotBackendSubmissionFailure]: ...


def _project_observation(
    observed: ObservedSnapshot,
    vm_identity: VirtualMachineIdentityPort,
    snapshot_identity: SnapshotIdentityPort,
) -> Result[Snapshot, SnapshotApplicationError]:
    owner = vm_identity.get_or_create_by_backend_ref(observed.owner_backend_ref)
    if isinstance(owner, Err):
        return Err(owner.error)
    public_id = snapshot_identity.get_or_create_snapshot(observed.backend_ref, owner.value)
    if isinstance(public_id, Err):
        return Err(public_id.error)
    return Ok(
        Snapshot(
            public_id.value, observed.name, ResourceReference("virtualMachines", str(owner.value))
        )
    )


def list_snapshots(
    port: SnapshotPort,
    vm_identity: VirtualMachineIdentityPort,
    snapshot_identity: SnapshotIdentityPort,
) -> Result[Sequence[Snapshot], SnapshotApplicationError]:
    listed = port.list_snapshots()
    if isinstance(listed, Err):
        return Err(listed.error)
    values: list[Snapshot] = []
    for item in listed.value:
        projected = _project_observation(item, vm_identity, snapshot_identity)
        if isinstance(projected, Err):
            return projected
        values.append(projected.value)
    return Ok(tuple(values))


def get_snapshot(  # noqa: PLR0911
    port: SnapshotPort,
    vm_identity: VirtualMachineIdentityPort,
    snapshot_identity: SnapshotIdentityPort,
    snapshot_id: SnapshotId,
) -> Result[Snapshot, SnapshotApplicationError]:
    mapping = snapshot_identity.get_snapshot_mapping(snapshot_id)
    if isinstance(mapping, Err):
        if isinstance(mapping.error, SnapshotIdentityNotFound):
            return Err(SnapshotNotFound(snapshot_id))
        return Err(mapping.error)
    observed = port.get_snapshot(mapping.value.backend_ref)
    if isinstance(observed, Err):
        if isinstance(observed.error, BackendSnapshotNotFound):
            return Err(SnapshotNotFound(snapshot_id))
        return Err(observed.error)
    if observed.value.backend_ref != mapping.value.backend_ref:
        return Err(
            SnapshotIdentityPersistenceFailure("get", "backend returned a different snapshot")
        )
    observed_owner = vm_identity.get_or_create_by_backend_ref(observed.value.owner_backend_ref)
    if isinstance(observed_owner, Err):
        return Err(observed_owner.error)
    if observed_owner.value != mapping.value.virtual_machine_id:
        return Err(SnapshotIdentityOwnerMismatch(mapping.value.backend_ref))
    return Ok(
        Snapshot(
            snapshot_id,
            observed.value.name,
            ResourceReference("virtualMachines", str(mapping.value.virtual_machine_id)),
        )
    )


def _persist(
    store: OperationStorePort, operation: Operation, backend_ref: BackendOperationRef
) -> Result[Operation, SnapshotApplicationError]:
    persisted = store.create_running(operation, backend_ref)
    if isinstance(persisted, Err):
        return Err(persisted.error)
    return Ok(persisted.value)


def create_snapshot(  # noqa: PLR0917
    port: SnapshotPort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
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
    return _persist(
        store,
        Operation(
            operation_id,
            ResourceReference("virtualMachines", str(virtual_machine_id)),
            "CREATE_SNAPSHOT",
            Running(),
        ),
        submitted.value,
    )


def delete_snapshot(
    port: SnapshotPort,
    identity: SnapshotIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    snapshot_id: SnapshotId,
) -> Result[Operation, SnapshotApplicationError]:
    mapping = identity.get_snapshot_mapping(snapshot_id)
    if isinstance(mapping, Err):
        if isinstance(mapping.error, SnapshotIdentityNotFound):
            return Err(SnapshotNotFound(snapshot_id))
        return Err(mapping.error)
    submitted = port.submit_delete_snapshot(mapping.value.backend_ref)
    if isinstance(submitted, Err):
        return Err(
            SnapshotCommandSubmissionFailure("delete", str(snapshot_id), submitted.error.reason)
        )
    return _persist(
        store,
        Operation(
            operation_id,
            ResourceReference("snapshots", str(snapshot_id)),
            "DELETE_SNAPSHOT",
            Running(),
        ),
        submitted.value,
    )
