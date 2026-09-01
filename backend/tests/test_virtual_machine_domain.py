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
            AcceptedPowerCommand(VirtualMachineId("vm-1"), PowerCommand.START),
            id="stopped-start-accepted",
        ),
        pytest.param(
            PowerState.RUNNING,
            PowerCommand.STOP,
            AcceptedPowerCommand(VirtualMachineId("vm-1"), PowerCommand.STOP),
            id="running-stop-accepted",
        ),
        pytest.param(
            PowerState.RUNNING,
            PowerCommand.START,
            AlreadyRunning(VirtualMachineId("vm-1")),
            id="running-start-rejected",
        ),
        pytest.param(
            PowerState.STOPPED,
            PowerCommand.STOP,
            AlreadyStopped(VirtualMachineId("vm-1")),
            id="stopped-stop-rejected",
        ),
    ],
)
def test_validate_power_command_table(
    state: PowerState,
    command: PowerCommand,
    expected: AcceptedPowerCommand | AlreadyRunning | AlreadyStopped,
) -> None:
    """
    Pure domain validation: test all state x command combinations.

    Expected behavior:
    - STOPPED + START -> Ok(accepted)
    - RUNNING + STOP -> Ok(accepted)
    - RUNNING + START -> Err(AlreadyRunning)
    - STOPPED + STOP -> Err(AlreadyStopped)

    Note: VM power state is NOT mutated by validation.
    """
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    result = validate_power_command(vm, command)
    if isinstance(expected, AcceptedPowerCommand):
        assert isinstance(result, Ok)
        assert result.value == expected
        # Verify VM remains unchanged
        assert vm.power_state is state
    else:
        assert isinstance(result, Err)
        assert result.error == expected
