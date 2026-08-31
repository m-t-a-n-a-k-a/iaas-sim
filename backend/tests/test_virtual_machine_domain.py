import pytest

from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
    transition,
)
from iaas_sim.result import Err, Ok


@pytest.mark.parametrize(
    ("state", "command", "expected"),
    [
        pytest.param(
            PowerState.STOPPED, PowerCommand.START, PowerState.RUNNING, id="stopped-starts"
        ),
        pytest.param(PowerState.RUNNING, PowerCommand.STOP, PowerState.STOPPED, id="running-stops"),
        pytest.param(
            PowerState.RUNNING,
            PowerCommand.START,
            AlreadyRunning,
            id="running-start-rejected",
        ),
        pytest.param(
            PowerState.STOPPED,
            PowerCommand.STOP,
            AlreadyStopped,
            id="stopped-stop-rejected",
        ),
    ],
)
def test_transition_table(
    state: PowerState,
    command: PowerCommand,
    expected: PowerState | type[AlreadyRunning] | type[AlreadyStopped],
) -> None:
    vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", state)
    result = transition(vm, command)
    if isinstance(expected, PowerState):
        assert isinstance(result, Ok)
        assert result.value.power_state is expected
    elif expected in (AlreadyRunning, AlreadyStopped):
        assert isinstance(result, Err)
        assert isinstance(result.error, expected)
