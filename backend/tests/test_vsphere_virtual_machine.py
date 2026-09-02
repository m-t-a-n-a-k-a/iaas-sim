import pytest

from iaas_sim.adapters.vsphere.virtual_machine import (
    project_virtual_machine,
    virtual_machine_property_filter,
)
from iaas_sim.domain.entity.virtual_machine import PowerState, VirtualMachine, VirtualMachineId


class FakeVirtualMachine:
    def PowerOnVM_Task(self) -> object:
        return object()

    def PowerOffVM_Task(self) -> object:
        return object()


def test_property_filter_requests_only_projection_fields() -> None:
    filter_spec = virtual_machine_property_filter(FakeVirtualMachine())
    filter_attributes = vars(filter_spec)
    property_specs = filter_attributes["propSet"]
    assert isinstance(property_specs, list)
    assert len(property_specs) == 1
    property_attributes = vars(property_specs[0])
    property_paths = property_attributes["pathSet"]

    assert property_paths == ["name", "summary.runtime.powerState"]


@pytest.mark.parametrize(
    ("backend_state", "expected"),
    [
        pytest.param("poweredOn", PowerState.RUNNING, id="powered-on"),
        pytest.param("poweredOff", PowerState.STOPPED, id="powered-off"),
    ],
)
def test_to_domain_projects_explicitly_collected_power_state(
    backend_state: str, expected: PowerState
) -> None:
    projected = project_virtual_machine(VirtualMachineId("vm-1"), "demo", backend_state)

    assert projected == VirtualMachine(VirtualMachineId("vm-1"), "demo", expected)


def test_to_domain_rejects_unsupported_backend_state() -> None:
    with pytest.raises(ValueError, match="unsupported power state: suspended"):
        project_virtual_machine(VirtualMachineId("vm-1"), "demo", "suspended")
