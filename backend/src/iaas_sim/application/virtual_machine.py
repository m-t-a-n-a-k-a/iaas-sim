from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.domain.entity.virtual_machine import (
    PowerCommand,
    TransitionError,
    VirtualMachine,
    VirtualMachineId,
    transition,
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


type ApplicationError = (
    VirtualMachineNotFound
    | VirtualMachineOperationFailure
    | VirtualMachineAdapterFailure
    | TransitionError
)


class VirtualMachinePort(Protocol):
    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]: ...

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[
        VirtualMachine,
        VirtualMachineNotFound | VirtualMachineAdapterFailure,
    ]: ...

    def power_on(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]: ...

    def power_off(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]: ...


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


def power_virtual_machine(
    port: VirtualMachinePort,
    virtual_machine_id: VirtualMachineId,
    command: PowerCommand,
) -> Result[VirtualMachine, ApplicationError]:
    loaded = port.get_virtual_machine(virtual_machine_id)
    if isinstance(loaded, Err):
        return Err[ApplicationError](loaded.error)

    transitioned = transition(loaded.value, command)
    if isinstance(transitioned, Err):
        return Err[ApplicationError](transitioned.error)

    operation = (
        port.power_on(virtual_machine_id)
        if command is PowerCommand.START
        else port.power_off(virtual_machine_id)
    )
    if isinstance(operation, Err):
        return Err[ApplicationError](operation.error)
    return Ok(transitioned.value)


def start_virtual_machine(
    port: VirtualMachinePort, virtual_machine_id: VirtualMachineId
) -> Result[VirtualMachine, ApplicationError]:
    return power_virtual_machine(port, virtual_machine_id, PowerCommand.START)


def stop_virtual_machine(
    port: VirtualMachinePort, virtual_machine_id: VirtualMachineId
) -> Result[VirtualMachine, ApplicationError]:
    return power_virtual_machine(port, virtual_machine_id, PowerCommand.STOP)
