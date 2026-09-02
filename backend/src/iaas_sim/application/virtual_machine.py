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
    OperationRegistryPort,
    TrackedOperation,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, Running
from iaas_sim.domain.entity.virtual_machine import (
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
    virtual_machine_id: VirtualMachineId | BackendVirtualMachineRef


@dataclass(frozen=True, slots=True)
class VirtualMachineBackendFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandSubmissionFailure:
    backend_ref: BackendVirtualMachineRef
    reason: str


type ApplicationError = (
    VirtualMachineNotFound
    | VirtualMachineBackendFailure
    | VirtualMachineIdentityPersistenceFailure
    | PowerCommandError
    | PowerCommandSubmissionFailure
)


class VirtualMachinePort(Protocol):
    def list_virtual_machines(
        self,
    ) -> Result[Sequence[ObservedVirtualMachine], VirtualMachineBackendFailure]: ...
    def get_virtual_machine(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[ObservedVirtualMachine, VirtualMachineNotFound | VirtualMachineBackendFailure]: ...
    def submit_power_command(
        self, backend_ref: BackendVirtualMachineRef, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandSubmissionFailure]: ...


def _identity_error(
    error: VirtualMachineIdentityError, public_id: VirtualMachineId
) -> ApplicationError:
    if isinstance(error, VirtualMachineIdentityNotFound):
        return VirtualMachineNotFound(public_id)
    return error


def list_virtual_machines(
    port: VirtualMachinePort, identity: VirtualMachineIdentityPort
) -> Result[Sequence[VirtualMachine], ApplicationError]:
    observed = port.list_virtual_machines()
    if isinstance(observed, Err):
        return Err(observed.error)
    projected: list[VirtualMachine] = []
    for vm in observed.value:
        mapped = identity.get_or_create_by_backend_ref(vm.backend_ref)
        if isinstance(mapped, Err):
            return Err(mapped.error)
        projected.append(VirtualMachine(mapped.value, vm.name, vm.power_state))
    return Ok(tuple(projected))


def get_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    virtual_machine_id: VirtualMachineId,
) -> Result[VirtualMachine, ApplicationError]:
    mapped = identity.get_backend_ref(virtual_machine_id)
    if isinstance(mapped, Err):
        return Err(_identity_error(mapped.error, virtual_machine_id))
    observed = port.get_virtual_machine(mapped.value)
    if isinstance(observed, Err):
        error = observed.error
        return Err(
            VirtualMachineNotFound(virtual_machine_id)
            if isinstance(error, VirtualMachineNotFound)
            else error
        )
    return Ok(VirtualMachine(virtual_machine_id, observed.value.name, observed.value.power_state))


def execute_power_command(  # noqa: PLR0917
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    command: PowerCommand,
) -> Result[Operation, ApplicationError]:
    mapped = identity.get_backend_ref(virtual_machine_id)
    if isinstance(mapped, Err):
        return Err(_identity_error(mapped.error, virtual_machine_id))
    backend_ref = mapped.value
    observed = port.get_virtual_machine(backend_ref)
    if isinstance(observed, Err):
        error = observed.error
        return Err(
            VirtualMachineNotFound(virtual_machine_id)
            if isinstance(error, VirtualMachineNotFound)
            else error
        )
    validated = validate_power_command(
        VirtualMachine(virtual_machine_id, observed.value.name, observed.value.power_state), command
    )
    if isinstance(validated, Err):
        return Err(validated.error)
    submitted = port.submit_power_command(backend_ref, validated.value.command)
    if isinstance(submitted, Err):
        return Err(submitted.error)
    tracked = TrackedOperation(
        operation_id,
        ResourceReference("virtualMachines", str(virtual_machine_id)),
        validated.value.command.value,
        submitted.value,
    )
    registry.add(tracked)
    return Ok(Operation(tracked.id, tracked.target, tracked.action, Running()))


def start_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, identity, registry, operation_id, virtual_machine_id, PowerCommand.START
    )


def stop_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, identity, registry, operation_id, virtual_machine_id, PowerCommand.STOP
    )
