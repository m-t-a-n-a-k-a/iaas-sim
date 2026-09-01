from dataclasses import dataclass

import pytest

from iaas_sim.adapters.vsphere.virtual_machine import (
    VsphereVirtualMachineObject,
    project_virtual_machine,
)
from iaas_sim.domain.entity.virtual_machine import PowerState, VirtualMachine, VirtualMachineId


@dataclass
class FakeRuntimeInfo:
    powerState: object


@dataclass
class FakeSummaryInfo:
    runtime: FakeRuntimeInfo


class FakeVirtualMachine:
    def __init__(self, power_state: str) -> None:
        self._moId = "vm-1"
        self.name = "demo"
        self.summary = FakeSummaryInfo(FakeRuntimeInfo(power_state))

    def PowerOnVM_Task(self) -> object:
        return object()

    def PowerOffVM_Task(self) -> object:
        return object()


@pytest.mark.parametrize(
    ("backend_state", "expected"),
    [
        pytest.param("poweredOn", PowerState.RUNNING, id="powered-on"),
        pytest.param("poweredOff", PowerState.STOPPED, id="powered-off"),
    ],
)
def test_to_domain_reads_observed_state_from_summary_runtime(
    backend_state: str, expected: PowerState
) -> None:
    vm = FakeVirtualMachine(backend_state)
    assert isinstance(vm, VsphereVirtualMachineObject)

    projected = project_virtual_machine(vm)

    assert projected == VirtualMachine(VirtualMachineId("vm-1"), "demo", expected)


def test_to_domain_rejects_unsupported_backend_state() -> None:
    vm = FakeVirtualMachine("suspended")
    assert isinstance(vm, VsphereVirtualMachineObject)

    with pytest.raises(ValueError, match="unsupported power state: suspended"):
        project_virtual_machine(vm)
