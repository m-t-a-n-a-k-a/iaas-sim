# pyright: strict

from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_type

from iaas_sim.application.identity import VirtualMachineIdentityPort
from iaas_sim.application.operation import OperationStorePort
from iaas_sim.application.virtual_machine import (
    ApplicationError,
    VirtualMachinePort,
    execute_power_command,
    get_virtual_machine,
    list_virtual_machines,
)
from iaas_sim.domain.entity.operation import Operation, OperationId
from iaas_sim.domain.entity.virtual_machine import PowerCommand, VirtualMachine, VirtualMachineId
from iaas_sim.result import Ok, Result, ResultUnwrapper, result_workflow


@dataclass(frozen=True)
class LowLevelError:
    message: str


@dataclass(frozen=True)
class PublicError:
    message: str


@dataclass(frozen=True)
class TypedFinalValue:
    value: str


def _to_public_error(error: LowLevelError) -> PublicError:
    return PublicError(error.message)


@result_workflow
def _mapped_heterogeneous_workflow(
    unwrap: ResultUnwrapper[PublicError],
) -> TypedFinalValue:
    integer_result: Result[int, LowLevelError] = Ok(3)
    integer = unwrap.map_error(integer_result, _to_public_error)
    assert_type(integer, int)

    text_result: Result[str, LowLevelError] = Ok(str(integer))
    text = unwrap.map_error(text_result, _to_public_error)
    assert_type(text, str)

    final_result: Result[TypedFinalValue, LowLevelError] = Ok(TypedFinalValue(text))
    final = unwrap.map_error(final_result, _to_public_error)
    assert_type(final, TypedFinalValue)
    return final


assert_type(_mapped_heterogeneous_workflow(), Result[TypedFinalValue, PublicError])


def assert_get_virtual_machine_signature(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    virtual_machine_id: VirtualMachineId,
) -> None:
    assert_type(
        get_virtual_machine(port, identity, virtual_machine_id),
        Result[VirtualMachine, ApplicationError],
    )


def assert_list_virtual_machines_signature(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
) -> None:
    assert_type(
        list_virtual_machines(port, identity),
        Result[Sequence[VirtualMachine], ApplicationError],
    )


def assert_execute_power_command_signature(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> None:
    assert_type(
        execute_power_command(
            port,
            identity,
            store,
            operation_id,
            virtual_machine_id,
            PowerCommand.START,
        ),
        Result[Operation, ApplicationError],
    )
