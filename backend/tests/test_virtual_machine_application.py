from collections.abc import Callable, Sequence
from uuid import uuid7

import pytest

from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.virtual_machine import (
    PowerCommandSubmissionFailure,
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
    VirtualMachinePort,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.operation import Operation, OperationId, ResourceReference, Running
from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

PowerUseCase = Callable[
    [VirtualMachinePort, InMemoryOperationRegistry, OperationId, VirtualMachineId],
    Result[Operation, object],
]


class FakeVirtualMachinePort:
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
        return (
            Ok(self.vm)
            if virtual_machine_id == self.vm.id
            else Err(VirtualMachineNotFound(virtual_machine_id))
        )

    def submit_power_command(
        self, virtual_machine_id: VirtualMachineId, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandSubmissionFailure]:
        if self.submit_failure is not None:
            return Err(self.submit_failure)
        self.submissions.append((virtual_machine_id, command))
        return Ok(BackendOperationRef("task-mock-mor"))


@pytest.mark.parametrize(
    ("state", "use_case", "command"),
    [
        pytest.param(
            PowerState.STOPPED, start_virtual_machine, PowerCommand.START, id="start-stopped"
        ),
        pytest.param(
            PowerState.RUNNING, stop_virtual_machine, PowerCommand.STOP, id="stop-running"
        ),
    ],
)
def test_valid_command_creates_and_tracks_operation(
    state: PowerState, use_case: PowerUseCase, command: PowerCommand
) -> None:
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    port, registry = FakeVirtualMachinePort(vm), InMemoryOperationRegistry()
    operation_id = OperationId(uuid7())

    result = use_case(port, registry, operation_id, vm.id)

    assert result == Ok(
        Operation(
            operation_id, ResourceReference("virtualMachines", "vm-1"), command.value, Running()
        )
    )
    tracked = registry.get(operation_id)
    assert tracked is not None
    assert tracked.backend_ref == BackendOperationRef("task-mock-mor")
    assert str(tracked.backend_ref) != str(operation_id.value)
    assert vm.power_state is state


@pytest.mark.parametrize(
    ("state", "use_case", "expected"),
    [
        pytest.param(
            PowerState.RUNNING,
            start_virtual_machine,
            AlreadyRunning(VirtualMachineId("vm-1")),
            id="start-running",
        ),
        pytest.param(
            PowerState.STOPPED,
            stop_virtual_machine,
            AlreadyStopped(VirtualMachineId("vm-1")),
            id="stop-stopped",
        ),
    ],
)
def test_err_stops_backend_side_effects(
    state: PowerState, use_case: PowerUseCase, expected: object
) -> None:
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    port, registry = FakeVirtualMachinePort(vm), InMemoryOperationRegistry()
    result = use_case(port, registry, OperationId(uuid7()), vm.id)
    assert result == Err(expected)
    assert port.submissions == []
