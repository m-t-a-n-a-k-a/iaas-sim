from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from iaas_sim.result import Err, Ok, Result

VirtualMachineId = NewType("VirtualMachineId", str)


class PowerState(StrEnum):
    """
    Observed power state of a VirtualMachine.

    Reflects the last-known state from the virtualization backend,
    not the desired state or the state of in-flight operations.
    """

    STOPPED = "STOPPED"
    RUNNING = "RUNNING"


class PowerCommand(StrEnum):
    """Power operation command."""

    START = "START"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class AlreadyRunning:
    """Validation error: attempted START on already-RUNNING VM."""

    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class AlreadyStopped:
    """Validation error: attempted STOP on already-STOPPED VM."""

    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class AcceptedPowerCommand:
    """
    Result of successful power command validation.

    Indicates the command is acceptable given current observed state.
    Does NOT indicate the command has been executed; only that it
    passed domain validation.
    """

    virtual_machine_id: VirtualMachineId
    command: PowerCommand


PowerCommandError = AlreadyRunning | AlreadyStopped


@dataclass(frozen=True, slots=True)
class VirtualMachine:
    """
    VirtualMachine Entity.

    Invariant: power_state represents the last-observed power state
    from the virtualization backend, not the desired state or
    the state of in-flight operations. Use Operation to track
    asynchronous command execution.
    """

    id: VirtualMachineId
    name: str
    power_state: PowerState


# State-command decision table for validation
_VALID_COMMANDS: dict[tuple[PowerState, PowerCommand], bool] = {
    (PowerState.STOPPED, PowerCommand.START): True,
    (PowerState.RUNNING, PowerCommand.STOP): True,
    (PowerState.RUNNING, PowerCommand.START): False,
    (PowerState.STOPPED, PowerCommand.STOP): False,
}

_ERROR_TYPES: dict[tuple[PowerState, PowerCommand], type[AlreadyRunning] | type[AlreadyStopped]] = {
    (PowerState.RUNNING, PowerCommand.START): AlreadyRunning,
    (PowerState.STOPPED, PowerCommand.STOP): AlreadyStopped,
}


def validate_power_command(
    vm: VirtualMachine,
    command: PowerCommand,
) -> Result[AcceptedPowerCommand, PowerCommandError]:
    """
    Pure domain validation: check if power command is valid for observed state.

    Does not mutate vm or issue backend commands.
    Returns:
        Ok(AcceptedPowerCommand): command is valid
        Err(PowerCommandError): validation failed (AlreadyRunning/AlreadyStopped)

    Railway: validation errors are expected failures, propagated as Err.
    """
    key = (vm.power_state, command)
    if _VALID_COMMANDS.get(key, False):
        return Ok(AcceptedPowerCommand(vm.id, command))

    error_type = _ERROR_TYPES.get(key)
    if error_type is AlreadyRunning:
        return Err(AlreadyRunning(vm.id))
    if error_type is AlreadyStopped:
        return Err(AlreadyStopped(vm.id))
    # Unreachable: state space is fully covered
    return Err(AlreadyStopped(vm.id))


# Deprecated: old transition() API kept for backwards compatibility during migration
def transition(
    vm: VirtualMachine,
    command: PowerCommand,
) -> Result[VirtualMachine, PowerCommandError]:
    """
    DEPRECATED: Use validate_power_command() instead.

    Old semantics mutated VM state immediately, violating observed-state invariant.
    This function is retained temporarily for test migration.
    """
    result = validate_power_command(vm, command)
    if isinstance(result, Err):
        return Err(result.error)
    # Note: Old behavior would have mutated state here.
    # New architecture does not mutate VM in response to command.
    return Ok(vm)
