from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.domain.entity.operation import Operation, OperationId, OperationState, VsphereTaskRef
from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    PowerCommandError,
    VirtualMachine,
    VirtualMachineId,
    validate_power_command,
)
from iaas_sim.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class VirtualMachineNotFound:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class VirtualMachineOperationFailure:
    virtual_machine_id: VirtualMachineId
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class VirtualMachineAdapterFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandSubmissionFailure:
    virtual_machine_id: VirtualMachineId
    reason: str


type ApplicationError = (
    VirtualMachineNotFound
    | VirtualMachineOperationFailure
    | VirtualMachineAdapterFailure
    | PowerCommandError
    | PowerCommandSubmissionFailure
)


class VirtualMachinePort(Protocol):
    """
    VirtualMachine resource operations.

    Separation:
    - get_virtual_machine(): returns observed VM state
    - submit_power_command(): issues async command, returns task reference
    """

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]: ...

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[
        VirtualMachine,
        VirtualMachineNotFound | VirtualMachineAdapterFailure,
    ]: ...

    def submit_power_command(
        self, virtual_machine_id: VirtualMachineId, command: PowerCommand
    ) -> Result[VsphereTaskRef, PowerCommandSubmissionFailure]: ...


def list_virtual_machines(
    port: VirtualMachinePort,
) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]:
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
    # Step 1: Load observed state
    loaded = port.get_virtual_machine(virtual_machine_id)
    if isinstance(loaded, Err):
        return Err[ApplicationError](loaded.error)

    # Step 2: Domain validation (pure, no side effects)
    validated = validate_power_command(loaded.value, command)
    if isinstance(validated, Err):
        return Err[ApplicationError](validated.error)

    # Step 3: Submit to backend
    submitted = port.submit_power_command(virtual_machine_id, command)
    if isinstance(submitted, Err):
        return Err[ApplicationError](submitted.error)

    # Step 4: Create Operation resource
    operation = Operation(
        id=operation_id,
        target_virtual_machine_id=virtual_machine_id,
        action=command.value,
        state=OperationState.RUNNING,
        failure=None,
    )
    return Ok(operation)


def start_virtual_machine(
    port: VirtualMachinePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(port, operation_id, virtual_machine_id, PowerCommand.START)


def stop_virtual_machine(
    port: VirtualMachinePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(port, operation_id, virtual_machine_id, PowerCommand.STOP)
