from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, Protocol

from iaas_sim.application.identity import BackendVirtualMachineRef
from iaas_sim.domain.entity.operation import Operation, OperationId
from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Result

BackendOperationRef = NewType("BackendOperationRef", str)


@dataclass(frozen=True, slots=True)
class BackendOperationRunning:
    pass


@dataclass(frozen=True, slots=True)
class BackendOperationNoResult:
    pass


@dataclass(frozen=True, slots=True)
class BackendVirtualMachineCreated:
    backend_ref: BackendVirtualMachineRef


type BackendOperationResult = BackendOperationNoResult | BackendVirtualMachineCreated


@dataclass(frozen=True, slots=True)
class BackendOperationSucceeded:
    result: BackendOperationResult = BackendOperationNoResult()


@dataclass(frozen=True, slots=True)
class BackendOperationFailed:
    reason: str


type BackendOperationStatus = (
    BackendOperationRunning | BackendOperationSucceeded | BackendOperationFailed
)


@dataclass(frozen=True, slots=True)
class StoredOperation:
    operation: Operation
    backend_ref: BackendOperationRef


@dataclass(frozen=True, slots=True)
class OperationNotFound:
    operation_id: OperationId


@dataclass(frozen=True, slots=True)
class OperationPersistenceFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class OperationPollingFailure:
    reason: str


type OperationStoreError = OperationNotFound | OperationPersistenceFailure


class OperationStorePort(Protocol):
    def create_running(
        self, operation: Operation, backend_ref: BackendOperationRef
    ) -> Result[Operation, OperationPersistenceFailure]: ...
    def get(self, operation_id: OperationId) -> Result[StoredOperation, OperationStoreError]: ...
    def complete(self, operation: Operation) -> Result[Operation, OperationStoreError]: ...


class VirtualMachineCreateFinalizerPort(Protocol):
    def finalize_virtual_machine_create(
        self,
        operation: Operation,
        virtual_machine_id: VirtualMachineId,
        backend_ref: BackendVirtualMachineRef,
    ) -> Result[Operation, OperationPersistenceFailure]: ...


class BackendOperationPort(Protocol):
    def get_operation_status(
        self, backend_ref: BackendOperationRef
    ) -> Result[BackendOperationStatus, OperationPollingFailure]: ...
