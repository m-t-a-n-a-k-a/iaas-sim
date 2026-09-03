import pytest

from iaas_sim.adapters.vsphere.adapter import (
    project_snapshots,
    project_virtual_machine,
    snapshot_property_filter,
    snapshot_roots,
    virtual_machine_property_filter,
)
from iaas_sim.application.identity import BackendSnapshotRef, BackendVirtualMachineRef
from iaas_sim.application.snapshot import ObservedSnapshot
from iaas_sim.application.virtual_machine import ObservedVirtualMachine
from iaas_sim.domain.entity.virtual_machine import PowerState


class FakeVirtualMachine:
    def PowerOnVM_Task(self) -> object:
        return object()

    def PowerOffVM_Task(self) -> object:
        return object()


class FakeDynamicProperty:
    def __init__(self, name: str, val: object) -> None:
        self.name = name
        self.val = val


class FakeObjectContent:
    def __init__(self, properties: list[FakeDynamicProperty]) -> None:
        self.propSet = properties


class FakePropertyCollector:
    def __init__(self, properties: list[FakeDynamicProperty]) -> None:
        self.properties = properties

    def RetrieveContents(self, specSet: list[object]) -> list[FakeObjectContent]:
        return [FakeObjectContent(self.properties)]


class FakeSnapshotObject:
    def __init__(self, snapshot_id: str) -> None:
        self._moId = snapshot_id


class FakeSnapshotNode:
    def __init__(self, snapshot_id: str, name: object, children: object = ()) -> None:
        self.snapshot = FakeSnapshotObject(snapshot_id)
        self.name = name
        self.childSnapshotList = children


def test_property_filter_requests_only_projection_fields() -> None:
    filter_spec = virtual_machine_property_filter(FakeVirtualMachine())
    filter_attributes = vars(filter_spec)
    property_specs = filter_attributes["propSet"]
    assert isinstance(property_specs, list)
    assert len(property_specs) == 1
    property_attributes = vars(property_specs[0])
    property_paths = property_attributes["pathSet"]

    assert property_paths == ["name", "summary.runtime.powerState", "config.extraConfig"]


def test_snapshot_property_filter_requests_only_tree_roots() -> None:
    filter_spec = snapshot_property_filter(FakeVirtualMachine())
    property_specs = vars(filter_spec)["propSet"]

    assert isinstance(property_specs, list)
    assert vars(property_specs[0])["pathSet"] == ["snapshot.rootSnapshotList"]


def test_absent_snapshot_property_means_no_snapshots() -> None:
    assert snapshot_roots(FakePropertyCollector([]), FakeVirtualMachine()) == ()


def test_snapshot_tree_is_projected_to_flat_domain_snapshots() -> None:
    child = FakeSnapshotNode("snapshot-2", "child")
    root = FakeSnapshotNode("snapshot-1", "root", (child,))
    roots = snapshot_roots(
        FakePropertyCollector([FakeDynamicProperty("snapshot.rootSnapshotList", (root,))]),
        FakeVirtualMachine(),
    )

    assert project_snapshots(BackendVirtualMachineRef("vm-1"), roots) == (
        ObservedSnapshot(
            BackendSnapshotRef("snapshot-1"), "root", BackendVirtualMachineRef("vm-1")
        ),
        ObservedSnapshot(
            BackendSnapshotRef("snapshot-2"), "child", BackendVirtualMachineRef("vm-1")
        ),
    )


@pytest.mark.parametrize(
    ("properties", "reason"),
    [
        pytest.param(
            [FakeDynamicProperty("snapshot.rootSnapshotList", object())],
            "malformed snapshot roots",
            id="non-sequence-roots",
        ),
        pytest.param(
            [FakeDynamicProperty("unexpected", ())],
            "malformed snapshot properties",
            id="unexpected-property",
        ),
    ],
)
def test_malformed_snapshot_property_fails(
    properties: list[FakeDynamicProperty], reason: str
) -> None:
    with pytest.raises(ValueError, match=reason):
        snapshot_roots(FakePropertyCollector(properties), FakeVirtualMachine())


def test_malformed_snapshot_tree_fails() -> None:
    with pytest.raises(ValueError, match="malformed snapshot tree"):
        project_snapshots(BackendVirtualMachineRef("vm-1"), (FakeSnapshotNode("snapshot-1", 1),))


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
    projected = project_virtual_machine(BackendVirtualMachineRef("vm-1"), "demo", backend_state)

    assert projected == ObservedVirtualMachine(BackendVirtualMachineRef("vm-1"), "demo", expected)


def test_to_domain_rejects_unsupported_backend_state() -> None:
    with pytest.raises(ValueError, match="unsupported power state: suspended"):
        project_virtual_machine(BackendVirtualMachineRef("vm-1"), "demo", "suspended")
