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
    match vm.power_state, command:
        case PowerState.STOPPED, PowerCommand.START:
            return Ok(AcceptedPowerCommand(vm.id, command))
        case PowerState.RUNNING, PowerCommand.STOP:
            return Ok(AcceptedPowerCommand(vm.id, command))
        case PowerState.RUNNING, PowerCommand.START:
            return Err(AlreadyRunning(vm.id))
        case PowerState.STOPPED, PowerCommand.STOP:
            return Err(AlreadyStopped(vm.id))
