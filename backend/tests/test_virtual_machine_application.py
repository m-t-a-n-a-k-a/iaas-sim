from collections.abc import Callable, Sequence
from uuid import uuid4

import pytest

from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
    VirtualMachinePort,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, OperationState, VsphereTaskRef
from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    PowerCommand,
    PowerCommandError,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

PowerUseCase = Callable[
    [VirtualMachinePort, OperationId, VirtualMachineId],
    Result[Operation, PowerCommandError | PowerCommandSubmissionFailure],
]


class FakeVirtualMachinePort:
    """Test port: async power commands, no mutation of VM state."""

    def __init__(self, vm: VirtualMachine) -> None:
        self.vm = vm
        self.submissions: list[tuple[VirtualMachineId, PowerCommand]] = []
        self.submit_failure: PowerCommandSubmissionFailure | None = None

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

    def submit_power_command(
        self, virtual_machine_id: VirtualMachineId, command: PowerCommand
    ) -> Result[VsphereTaskRef, PowerCommandSubmissionFailure]:
        if self.submit_failure:
            return Err(self.submit_failure)
        self.submissions.append((virtual_machine_id, command))
        return Ok(VsphereTaskRef("task-mock-mor"))


@pytest.mark.parametrize(
    ("state", "command_func", "expected_command"),
    [
        pytest.param(
            PowerState.STOPPED,
            start_virtual_machine,
            PowerCommand.START,
            id="start-stopped-vm",
        ),
        pytest.param(
            PowerState.RUNNING,
            stop_virtual_machine,
            PowerCommand.STOP,
            id="stop-running-vm",
        ),
    ],
)
def test_power_use_case_returns_operation(
    state: PowerState,
    command_func: PowerUseCase,
    expected_command: PowerCommand,
) -> None:
    """
    Valid power command flow:
    1. Domain validation passes
    2. Backend submission succeeds
    3. Operation returned with RUNNING state
    4. No VM state mutation
    """
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    port = FakeVirtualMachinePort(vm)
    operation_id = OperationId(uuid4())

    result = command_func(port, operation_id, vm.id)

    assert isinstance(result, Ok)
    operation = result.value
    assert operation.id == operation_id
    assert operation.target_virtual_machine_id == vm.id
    assert operation.action == expected_command.value
    assert operation.state == OperationState.RUNNING
    assert operation.failure is None
    assert port.submissions == [(vm.id, expected_command)]
    # Critical: VM state unchanged
    assert port.vm.power_state is state


@pytest.mark.parametrize(
    ("state", "command_func", "expected_error_type"),
    [
        pytest.param(
            PowerState.RUNNING,
            start_virtual_machine,
            AlreadyRunning,
            id="start-running-rejected",
        ),
        pytest.param(
            PowerState.STOPPED,
            stop_virtual_machine,
            AlreadyStopped,
            id="stop-stopped-rejected",
        ),
    ],
)
def test_rejected_command_does_not_call_port(
    state: PowerState,
    command_func: PowerUseCase,
    expected_error_type: type[PowerCommandError],
) -> None:
    """
    Validation failure:
    1. Domain validation fails
    2. Backend submission NOT called
    3. Err returned with appropriate error
    """
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    port = FakeVirtualMachinePort(vm)
    operation_id = OperationId(uuid4())

    result = command_func(port, operation_id, vm.id)

    assert isinstance(result, Err)
    assert isinstance(result.error, expected_error_type)
    assert port.submissions == []


def test_submission_failure_returns_error() -> None:
    """
    Backend submission failure:
    1. Validation passes
    2. Backend submit_power_command fails
    3. Err returned (not Operation)
    """
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.STOPPED)
    port = FakeVirtualMachinePort(vm)
    port.submit_failure = PowerCommandSubmissionFailure(vm.id, "backend unavailable")
    operation_id = OperationId(uuid4())

    result = start_virtual_machine(port, operation_id, vm.id)

    assert isinstance(result, Err)
    assert isinstance(result.error, PowerCommandSubmissionFailure)
