from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.identity import (
    BackendSnapshotRef,
    BackendVirtualMachineRef,
    SnapshotIdentityMapping,
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
from iaas_sim.result import Err, Ok, Result, and_then, map, map_error


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


def _as_application_error(error: SnapshotApplicationError) -> SnapshotApplicationError:
    return error


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
    return map_error(
        and_then(
            owner,
            lambda owner_id: map(
                snapshot_identity.get_or_create_snapshot(observed.backend_ref, owner_id),
                lambda public_id: Snapshot(
                    public_id,
                    observed.name,
                    ResourceReference("virtualMachines", str(owner_id)),
                ),
            ),
        ),
        _as_application_error,
    )


def list_snapshots(
    port: SnapshotPort,
    vm_identity: VirtualMachineIdentityPort,
    snapshot_identity: SnapshotIdentityPort,
) -> Result[Sequence[Snapshot], SnapshotApplicationError]:
    def project_all(
        observations: Sequence[ObservedSnapshot],
    ) -> Result[Sequence[Snapshot], SnapshotApplicationError]:
        values: list[Snapshot] = []
        for item in observations:
            projected = _project_observation(item, vm_identity, snapshot_identity)
            if isinstance(projected, Err):
                return projected
            values.append(projected.value)
        return Ok(tuple(values))

    return and_then(port.list_snapshots(), project_all)


def get_snapshot(
    port: SnapshotPort,
    vm_identity: VirtualMachineIdentityPort,
    snapshot_identity: SnapshotIdentityPort,
    snapshot_id: SnapshotId,
) -> Result[Snapshot, SnapshotApplicationError]:
    def map_identity_error(error: SnapshotIdentityNotFound | SnapshotIdentityPersistenceFailure):
        if isinstance(error, SnapshotIdentityNotFound):
            return SnapshotNotFound(snapshot_id)
        return error

    def load_observation(mapping: SnapshotIdentityMapping):
        return map(
            map_error(
                port.get_snapshot(mapping.backend_ref),
                lambda error: (
                    SnapshotNotFound(snapshot_id)
                    if isinstance(error, BackendSnapshotNotFound)
                    else error
                ),
            ),
            lambda observed: (mapping, observed),
        )

    def verify_backend_identity(value: tuple[SnapshotIdentityMapping, ObservedSnapshot]):
        mapping, observed = value
        if observed.backend_ref != mapping.backend_ref:
            return Err(
                SnapshotIdentityPersistenceFailure("get", "backend returned a different snapshot")
            )
        return Ok(value)

    def resolve_owner(value: tuple[SnapshotIdentityMapping, ObservedSnapshot]):
        mapping, observed = value
        return map(
            vm_identity.get_or_create_by_backend_ref(observed.owner_backend_ref),
            lambda owner_id: (mapping, observed, owner_id),
        )

    def project(value: tuple[SnapshotIdentityMapping, ObservedSnapshot, VirtualMachineId]):
        mapping, observed, owner_id = value
        if owner_id != mapping.virtual_machine_id:
            return Err(SnapshotIdentityOwnerMismatch(mapping.backend_ref))
        return Ok(
            Snapshot(
                snapshot_id,
                observed.name,
                ResourceReference("virtualMachines", str(mapping.virtual_machine_id)),
            )
        )

    loaded = map_error(snapshot_identity.get_snapshot_mapping(snapshot_id), map_identity_error)
    observed = and_then(loaded, load_observation)
    verified = and_then(observed, verify_backend_identity)
    owner = and_then(verified, resolve_owner)
    return map_error(and_then(owner, project), _as_application_error)


def _persist(
    store: OperationStorePort, operation: Operation, backend_ref: BackendOperationRef
) -> Result[Operation, SnapshotApplicationError]:
    return map_error(store.create_running(operation, backend_ref), _as_application_error)


def create_snapshot(  # noqa: PLR0917
    port: SnapshotPort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    name: str,
) -> Result[Operation, SnapshotApplicationError]:
    operation = Operation(
        operation_id,
        ResourceReference("virtualMachines", str(virtual_machine_id)),
        "CREATE_SNAPSHOT",
        Running(),
    )
    submitted = and_then(
        identity.get_backend_ref(virtual_machine_id),
        lambda backend_ref: map_error(
            port.submit_create_snapshot(backend_ref, name),
            lambda error: SnapshotCommandSubmissionFailure(
                "create", str(virtual_machine_id), error.reason
            ),
        ),
    )
    return and_then(submitted, lambda backend_ref: _persist(store, operation, backend_ref))


def delete_snapshot(
    port: SnapshotPort,
    identity: SnapshotIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    snapshot_id: SnapshotId,
) -> Result[Operation, SnapshotApplicationError]:
    operation = Operation(
        operation_id,
        ResourceReference("snapshots", str(snapshot_id)),
        "DELETE_SNAPSHOT",
        Running(),
    )
    mapped = map_error(
        identity.get_snapshot_mapping(snapshot_id),
        lambda error: (
            SnapshotNotFound(snapshot_id) if isinstance(error, SnapshotIdentityNotFound) else error
        ),
    )
    submitted = and_then(
        mapped,
        lambda mapping: map_error(
            port.submit_delete_snapshot(mapping.backend_ref),
            lambda error: SnapshotCommandSubmissionFailure(
                "delete", str(snapshot_id), error.reason
            ),
        ),
    )
    return and_then(submitted, lambda backend_ref: _persist(store, operation, backend_ref))
