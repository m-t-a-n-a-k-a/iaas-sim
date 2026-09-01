import pytest

from iaas_sim.domain.entity.virtual_machine import (
    AcceptedPowerCommand,
    AlreadyRunning,
    AlreadyStopped,
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
    validate_power_command,
)
from iaas_sim.result import Err, Ok


@pytest.mark.parametrize(
    ("state", "command", "expected"),
    [
        pytest.param(
            PowerState.STOPPED,
            PowerCommand.START,
            Ok(AcceptedPowerCommand(VirtualMachineId("vm-1"), PowerCommand.START)),
            id="stopped-start-accepted",
        ),
        pytest.param(
            PowerState.RUNNING,
            PowerCommand.STOP,
            Ok(AcceptedPowerCommand(VirtualMachineId("vm-1"), PowerCommand.STOP)),
            id="running-stop-accepted",
        ),
        pytest.param(
            PowerState.RUNNING,
            PowerCommand.START,
            Err(AlreadyRunning(VirtualMachineId("vm-1"))),
            id="running-start-rejected",
        ),
        pytest.param(
            PowerState.STOPPED,
            PowerCommand.STOP,
            Err(AlreadyStopped(VirtualMachineId("vm-1"))),
            id="stopped-stop-rejected",
        ),
    ],
)
def test_validate_power_command_table(
    state: PowerState,
    command: PowerCommand,
    expected: Ok[AcceptedPowerCommand] | Err[AlreadyRunning | AlreadyStopped],
) -> None:
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    assert validate_power_command(vm, command) == expected
    assert vm.power_state is state
