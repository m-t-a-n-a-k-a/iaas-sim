# pyright: strict

from typing import assert_type

from iaas_sim.application.identity import VirtualMachineIdentityPort
from iaas_sim.application.operation import OperationStorePort
from iaas_sim.application.virtual_machine import (
    ApplicationError,
    VirtualMachinePort,
    execute_power_command,
)
from iaas_sim.domain.entity.operation import Operation, OperationId
from iaas_sim.domain.entity.virtual_machine import PowerCommand, VirtualMachineId
from iaas_sim.result import Result


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
