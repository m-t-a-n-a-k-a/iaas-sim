from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, Protocol

from iaas_sim.domain.entity.operation import OperationId
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Result

BackendOperationRef = NewType("BackendOperationRef", str)


@dataclass(frozen=True, slots=True)
class BackendOperationRunning:
    pass


@dataclass(frozen=True, slots=True)
class BackendOperationSucceeded:
    pass


@dataclass(frozen=True, slots=True)
class BackendOperationFailed:
    reason: str


type BackendOperationStatus = (
    BackendOperationRunning | BackendOperationSucceeded | BackendOperationFailed
)


@dataclass(frozen=True, slots=True)
class TrackedOperation:
    id: OperationId
    target: ResourceReference
    action: str
    backend_ref: BackendOperationRef


@dataclass(frozen=True, slots=True)
class OperationNotFound:
    operation_id: OperationId


@dataclass(frozen=True, slots=True)
class OperationPollingFailure:
    reason: str


class OperationRegistryPort(Protocol):
    def add(self, operation: TrackedOperation) -> None: ...
    def get(self, operation_id: OperationId) -> TrackedOperation | None: ...


class BackendOperationPort(Protocol):
    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]: ...
