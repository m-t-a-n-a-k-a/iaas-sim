from collections.abc import Callable, Sequence

import pytest

from iaas_sim.application.virtual_machine import (
    ApplicationError,
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
    VirtualMachineOperationFailure,
    VirtualMachinePort,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.virtual_machine import PowerState, VirtualMachine, VirtualMachineId
from iaas_sim.result import Err, Ok, Result

PowerUseCase = Callable[
    [VirtualMachinePort, VirtualMachineId],
    Result[VirtualMachine, ApplicationError],
]


class FakeVirtualMachinePort:
    def __init__(self, vm: VirtualMachine) -> None:
        self.vm = vm
        self.operations: list[str] = []

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]:
        return Ok((self.vm,))

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[VirtualMachine, VirtualMachineNotFound | VirtualMachineAdapterFailure]:
        if virtual_machine_id != self.vm.id:
            return Err(VirtualMachineNotFound(virtual_machine_id))
        return Ok(self.vm)

    def power_on(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]:
        self.operations.append("start")
        return Ok(None)

    def power_off(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]:
        self.operations.append("stop")
        return Ok(None)


@pytest.mark.parametrize(
    ("state", "command", "expected_state", "expected_operation"),
    [
        pytest.param(
            PowerState.STOPPED,
            start_virtual_machine,
            PowerState.RUNNING,
            "start",
            id="start-stopped",
        ),
        pytest.param(
            PowerState.RUNNING,
            stop_virtual_machine,
            PowerState.STOPPED,
            "stop",
            id="stop-running",
        ),
    ],
)
def test_power_use_case_composes_domain_and_port(
    state: PowerState,
    command: PowerUseCase,
    expected_state: PowerState,
    expected_operation: str,
) -> None:
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    port = FakeVirtualMachinePort(vm)
    result = command(port, vm.id)
    assert isinstance(result, Ok)
    assert result.value.power_state is expected_state
    assert port.operations == [expected_operation]


def test_rejected_transition_does_not_call_port() -> None:
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.RUNNING)
    port = FakeVirtualMachinePort(vm)
    result = start_virtual_machine(port, vm.id)
    assert isinstance(result, Err)
    assert port.operations == []
