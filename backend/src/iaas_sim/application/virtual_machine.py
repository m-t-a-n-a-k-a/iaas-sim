from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationRegistryPort,
    TrackedOperation,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, ResourceReference, Running
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerCommandError,
    VirtualMachine,
    VirtualMachineId,
    validate_power_command,
)
from iaas_sim.result import Err, Ok, Result, and_then, map


@dataclass(frozen=True, slots=True)
class VirtualMachineNotFound:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class VirtualMachineBackendFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandSubmissionFailure:
    virtual_machine_id: VirtualMachineId
    reason: str


type ApplicationError = (
    VirtualMachineNotFound
    | VirtualMachineBackendFailure
    | PowerCommandError
    | PowerCommandSubmissionFailure
)


class VirtualMachinePort(Protocol):
    """
    VirtualMachine resource operations.

    Separation:
    - get_virtual_machine(): returns observed VM state
    - submit_power_command(): issues async command, returns a backend operation reference
    """

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineBackendFailure]: ...

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[
        VirtualMachine,
        VirtualMachineNotFound | VirtualMachineBackendFailure,
    ]: ...

    def submit_power_command(
        self, virtual_machine_id: VirtualMachineId, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandSubmissionFailure]: ...


def list_virtual_machines(
    port: VirtualMachinePort,
) -> Result[Sequence[VirtualMachine], VirtualMachineBackendFailure]:
    return port.list_virtual_machines()


def get_virtual_machine(
    port: VirtualMachinePort,
    virtual_machine_id: VirtualMachineId,
) -> Result[VirtualMachine, ApplicationError]:
    result = port.get_virtual_machine(virtual_machine_id)
    if isinstance(result, Err):
        return Err[ApplicationError](result.error)
    return Ok(result.value)


def execute_power_command(
    port: VirtualMachinePort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    command: PowerCommand,
) -> Result[Operation, ApplicationError]:
    """
    Railway: execute async power command.

    Flow:
      1. Load observed VM state
      2. Validate command against observed state (pure domain logic)
      3. Submit command to backend
      4. Create Operation tracking the submission

    Each step propagates Err, stopping further execution.
    """
    loaded = port.get_virtual_machine(virtual_machine_id)
    validated = and_then(
        loaded, lambda virtual_machine: validate_power_command(virtual_machine, command)
    )
    submitted = and_then(
        validated,
        lambda _virtual_machine: port.submit_power_command(virtual_machine_id, command),
    )
    tracked = map(
        submitted,
        lambda backend_ref: TrackedOperation(
            id=operation_id,
            target=ResourceReference("virtualMachines", str(virtual_machine_id)),
            action=command.value,
            backend_ref=backend_ref,
        ),
    )

    def register(operation: TrackedOperation) -> Result[Operation, ApplicationError]:
        registry.add(operation)
        return Ok(Operation(operation.id, operation.target, operation.action, Running()))

    return and_then(tracked, register)


def start_virtual_machine(
    port: VirtualMachinePort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, registry, operation_id, virtual_machine_id, PowerCommand.START
    )


def stop_virtual_machine(
    port: VirtualMachinePort,
    registry: OperationRegistryPort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, registry, operation_id, virtual_machine_id, PowerCommand.STOP
    )
