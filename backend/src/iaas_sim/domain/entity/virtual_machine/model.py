from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from iaas_sim.result import Err, Ok, Result

VirtualMachineId = NewType("VirtualMachineId", str)


class PowerState(StrEnum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"


class PowerCommand(StrEnum):
    START = "START"
    STOP = "STOP"


@dataclass(frozen=True, slots=True)
class AlreadyRunning:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class AlreadyStopped:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class InvalidTransition:
    virtual_machine_id: VirtualMachineId
    state: PowerState
    command: PowerCommand


TransitionError = AlreadyRunning | AlreadyStopped | InvalidTransition


@dataclass(frozen=True, slots=True)
class VirtualMachine:
    id: VirtualMachineId
    name: str
    power_state: PowerState


_TRANSITIONS: dict[
    tuple[PowerState, PowerCommand],
    PowerState,
] = {
    (PowerState.STOPPED, PowerCommand.START): PowerState.RUNNING,
    (PowerState.RUNNING, PowerCommand.STOP): PowerState.STOPPED,
}

_TRANSITION_ERRORS: dict[
    tuple[PowerState, PowerCommand], type[AlreadyRunning] | type[AlreadyStopped]
] = {
    (PowerState.RUNNING, PowerCommand.START): AlreadyRunning,
    (PowerState.STOPPED, PowerCommand.STOP): AlreadyStopped,
}


def transition(
    vm: VirtualMachine,
    command: PowerCommand,
) -> Result[VirtualMachine, TransitionError]:
    key = (vm.power_state, command)
    if key in _TRANSITIONS:
        return Ok(VirtualMachine(vm.id, vm.name, _TRANSITIONS[key]))
    error_type = _TRANSITION_ERRORS.get(key)
    if error_type is AlreadyRunning:
        return Err(AlreadyRunning(vm.id))
    if error_type is AlreadyStopped:
        return Err(AlreadyStopped(vm.id))
    return Err(InvalidTransition(vm.id, vm.power_state, command))
