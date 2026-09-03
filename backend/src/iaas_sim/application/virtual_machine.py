from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.identity import (
    BackendVirtualMachineRef,
    VirtualMachineIdentityError,
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
from iaas_sim.domain.entity.virtual_machine import (
    AcceptedPowerCommand,
    PowerCommand,
    PowerCommandError,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
    validate_power_command,
)
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class ObservedVirtualMachine:
    backend_ref: BackendVirtualMachineRef
    name: str
    power_state: PowerState


@dataclass(frozen=True, slots=True)
class VirtualMachineNotFound:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class VirtualMachineBackendNotFound:
    backend_ref: BackendVirtualMachineRef


@dataclass(frozen=True, slots=True)
class VirtualMachineBackendFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandSubmissionFailure:
    virtual_machine_id: VirtualMachineId
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandBackendSubmissionFailure:
    backend_ref: BackendVirtualMachineRef
    reason: str


@dataclass(frozen=True, slots=True)
class VirtualMachineCreateSpec:
    """Resolved, backend-independent inputs for creating a blank VM."""

    name: str
    vcpus: int
    memory_mib: int


@dataclass(frozen=True, slots=True)
class InvalidVirtualMachineCreateSpec:
    reason: str


@dataclass(frozen=True, slots=True)
class VirtualMachineCreateBackendSubmissionFailure:
    reason: str


def validate_virtual_machine_create_spec(
    spec: VirtualMachineCreateSpec,
) -> Result[VirtualMachineCreateSpec, InvalidVirtualMachineCreateSpec]:
    """Apply only the backend-independent minimum required create validation."""
    if spec.name == "":
        return Err(InvalidVirtualMachineCreateSpec("name must not be empty"))
    if spec.vcpus <= 0 or spec.memory_mib <= 0:
        return Err(InvalidVirtualMachineCreateSpec("sizing must be positive"))
    return Ok(spec)


type ApplicationError = (
    VirtualMachineNotFound
    | VirtualMachineBackendFailure
    | VirtualMachineIdentityPersistenceFailure
    | PowerCommandError
    | PowerCommandSubmissionFailure
    | OperationPersistenceFailure
)


class VirtualMachinePort(Protocol):
    def list_virtual_machines(
        self,
    ) -> Result[Sequence[ObservedVirtualMachine], VirtualMachineBackendFailure]: ...
    def get_virtual_machine(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[
        ObservedVirtualMachine, VirtualMachineBackendNotFound | VirtualMachineBackendFailure
    ]: ...
    def submit_power_command(
        self, backend_ref: BackendVirtualMachineRef, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandBackendSubmissionFailure]: ...
    def submit_create_virtual_machine(
        self, spec: VirtualMachineCreateSpec
    ) -> Result[BackendOperationRef, VirtualMachineCreateBackendSubmissionFailure]: ...


def _identity_error(
    error: VirtualMachineIdentityError, public_id: VirtualMachineId
) -> ApplicationError:
    if isinstance(error, VirtualMachineIdentityNotFound):
        return VirtualMachineNotFound(public_id)
    return error


def list_virtual_machines(
    port: VirtualMachinePort, identity: VirtualMachineIdentityPort
) -> Result[Sequence[VirtualMachine], ApplicationError]:
    listed = port.list_virtual_machines()
    if isinstance(listed, Err):
        return Err[ApplicationError](listed.error)

    projected: list[VirtualMachine] = []
    for vm in listed.value:
        mapped = identity.get_or_create_by_backend_ref(vm.backend_ref)
        if isinstance(mapped, Err):
            return Err[ApplicationError](mapped.error)
        projected.append(VirtualMachine(mapped.value, vm.name, vm.power_state))
    return Ok(tuple(projected))


def get_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    virtual_machine_id: VirtualMachineId,
) -> Result[VirtualMachine, ApplicationError]:
    resolved = identity.get_backend_ref(virtual_machine_id)
    if isinstance(resolved, Err):
        return Err(_identity_error(resolved.error, virtual_machine_id))

    observed = port.get_virtual_machine(resolved.value)
    if isinstance(observed, Err):
        if isinstance(observed.error, VirtualMachineBackendNotFound):
            return Err(VirtualMachineNotFound(virtual_machine_id))
        return Err[ApplicationError](observed.error)

    return Ok(VirtualMachine(virtual_machine_id, observed.value.name, observed.value.power_state))


def execute_power_command(  # noqa: PLR0911, PLR0917
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    command: PowerCommand,
) -> Result[Operation, ApplicationError]:
    resolved = identity.get_backend_ref(virtual_machine_id)
    if isinstance(resolved, Err):
        return Err(_identity_error(resolved.error, virtual_machine_id))
    backend_ref = resolved.value

    observed = port.get_virtual_machine(backend_ref)
    if isinstance(observed, Err):
        if isinstance(observed.error, VirtualMachineBackendNotFound):
            return Err(VirtualMachineNotFound(virtual_machine_id))
        return Err[ApplicationError](observed.error)

    validated = validate_power_command(
        VirtualMachine(
            virtual_machine_id,
            observed.value.name,
            observed.value.power_state,
        ),
        command,
    )
    if isinstance(validated, Err):
        return Err[ApplicationError](validated.error)
    accepted: AcceptedPowerCommand = validated.value

    submitted = port.submit_power_command(backend_ref, accepted.command)
    if isinstance(submitted, Err):
        return Err(PowerCommandSubmissionFailure(virtual_machine_id, submitted.error.reason))

    operation = Operation(
        operation_id,
        ResourceReference("virtualMachines", str(virtual_machine_id)),
        accepted.command.value,
        Running(),
    )
    persisted = store.create_running(operation, submitted.value)
    if isinstance(persisted, Err):
        return Err[ApplicationError](persisted.error)
    return persisted


def start_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, identity, store, operation_id, virtual_machine_id, PowerCommand.START
    )


def stop_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, identity, store, operation_id, virtual_machine_id, PowerCommand.STOP
    )
