from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, Protocol

from iaas_sim.domain.entity.snapshot import SnapshotId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Result

BackendVirtualMachineRef = NewType("BackendVirtualMachineRef", str)
BackendSnapshotRef = NewType("BackendSnapshotRef", str)


@dataclass(frozen=True, slots=True)
class VirtualMachineIdentityNotFound:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class VirtualMachineIdentityPersistenceFailure:
    operation: str
    reason: str


type VirtualMachineIdentityError = (
    VirtualMachineIdentityNotFound | VirtualMachineIdentityPersistenceFailure
)


class VirtualMachineIdentityPort(Protocol):
    def find_by_backend_ref(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[VirtualMachineId | None, VirtualMachineIdentityPersistenceFailure]: ...

    def get_or_create_by_backend_ref(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[VirtualMachineId, VirtualMachineIdentityPersistenceFailure]: ...

    def get_backend_ref(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[BackendVirtualMachineRef, VirtualMachineIdentityError]: ...


@dataclass(frozen=True, slots=True)
class SnapshotIdentityMapping:
    backend_ref: BackendSnapshotRef
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class SnapshotIdentityNotFound:
    snapshot_id: SnapshotId


@dataclass(frozen=True, slots=True)
class SnapshotIdentityPersistenceFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class SnapshotIdentityOwnerMismatch:
    backend_ref: BackendSnapshotRef


type SnapshotIdentityError = SnapshotIdentityNotFound | SnapshotIdentityPersistenceFailure
type SnapshotIdentityCreationError = (
    SnapshotIdentityPersistenceFailure | SnapshotIdentityOwnerMismatch
)


class SnapshotIdentityPort(Protocol):
    def get_or_create_snapshot(
        self, backend_ref: BackendSnapshotRef, virtual_machine_id: VirtualMachineId
    ) -> Result[SnapshotId, SnapshotIdentityCreationError]: ...

    def get_snapshot_mapping(
        self, snapshot_id: SnapshotId
    ) -> Result[SnapshotIdentityMapping, SnapshotIdentityError]: ...
