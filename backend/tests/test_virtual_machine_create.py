# ruff: noqa: PLR2004
# pyright: basic, reportArgumentType=false, reportIncompatibleMethodOverride=false
from __future__ import annotations

import pytest

from iaas_sim.adapters.vsphere.adapter import (
    VSphereAdapter,
    VsphereCreatePlacement,
)
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.virtual_machine import (
    InvalidVirtualMachineCreateSpec,
    VirtualMachineCreateBackendSubmissionFailure,
    VirtualMachineCreateSpec,
    validate_virtual_machine_create_spec,
)
from iaas_sim.result import Err, Ok


class FakeTask:
    _moId = "task-42"


class FakeFolder:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.configs: list[object] = []
        self.pools: list[object] = []
        self.power_on_calls = 0

    def CreateVM_Task(self, config: object, pool: object) -> object:
        self.configs.append(config)
        self.pools.append(pool)
        if self.failure is not None:
            raise self.failure
        return FakeTask()

    def PowerOnVM_Task(self) -> object:
        self.power_on_calls += 1
        return FakeTask()


class FakeServiceInstance:
    def RetrieveContent(self) -> object:
        return object()


class SubmissionAdapter(VSphereAdapter):
    def __init__(self, folder: FakeFolder, placement_available: bool = True) -> None:
        self.folder = folder
        self.placement_available = placement_available
        self.pool = object()

    def _connect(self) -> FakeServiceInstance:
        return FakeServiceInstance()

    def _default_create_placement(self, content: object) -> VsphereCreatePlacement:
        if not self.placement_available:
            raise ValueError("default VM placement unavailable")
        return VsphereCreatePlacement(self.folder, self.pool, "datastore-a")


def test_create_spec_preserves_resolved_values() -> None:
    spec = VirtualMachineCreateSpec("vm-01", 1, 1024)

    result = validate_virtual_machine_create_spec(spec)

    assert result == Ok(spec)
    assert isinstance(result, Ok)
    assert result.value.name == "vm-01"
    assert result.value.vcpus == 1
    assert result.value.memory_mib == 1024


@pytest.mark.parametrize(
    "spec",
    [
        pytest.param(VirtualMachineCreateSpec("", 1, 1024), id="empty-name"),
        pytest.param(VirtualMachineCreateSpec("vm", 0, 1024), id="zero-vcpus"),
        pytest.param(VirtualMachineCreateSpec("vm", 1, 0), id="zero-memory"),
    ],
)
def test_create_spec_rejects_invalid_minimums(spec: VirtualMachineCreateSpec) -> None:
    assert isinstance(validate_virtual_machine_create_spec(spec), Err)


def test_submit_create_vm_builds_blank_config_and_returns_task_ref() -> None:
    folder = FakeFolder()
    adapter = SubmissionAdapter(folder)

    result = adapter.submit_create_virtual_machine(VirtualMachineCreateSpec("vm-01", 2, 2048))

    assert result == Ok(BackendOperationRef("task-42"))
    assert len(folder.configs) == 1
    config = folder.configs[0]
    assert object.__getattribute__(config, "name") == "vm-01"
    assert object.__getattribute__(config, "numCPUs") == 2
    assert object.__getattribute__(config, "memoryMB") == 2048
    assert object.__getattribute__(config, "guestId") == "otherGuest64"
    files = object.__getattribute__(config, "files")
    assert object.__getattribute__(files, "vmPathName") == "[datastore-a]"
    assert folder.pools == [adapter.pool]
    assert folder.power_on_calls == 0


def test_unavailable_placement_is_a_typed_submission_failure() -> None:
    result = SubmissionAdapter(
        FakeFolder(), placement_available=False
    ).submit_create_virtual_machine(VirtualMachineCreateSpec("vm-01", 1, 1024))

    assert result == Err(
        VirtualMachineCreateBackendSubmissionFailure("default VM placement unavailable")
    )


def test_create_task_exception_is_a_typed_submission_failure() -> None:
    result = SubmissionAdapter(
        FakeFolder(RuntimeError("submission failed"))
    ).submit_create_virtual_machine(VirtualMachineCreateSpec("vm-01", 1, 1024))

    assert result == Err(VirtualMachineCreateBackendSubmissionFailure("submission failed"))


def test_empty_name_is_rejected_before_backend_access() -> None:
    folder = FakeFolder()
    result = SubmissionAdapter(folder).submit_create_virtual_machine(
        VirtualMachineCreateSpec("", 1, 1024)
    )

    assert result == Err(VirtualMachineCreateBackendSubmissionFailure("name must not be empty"))
    assert folder.configs == []
    validated = validate_virtual_machine_create_spec(VirtualMachineCreateSpec("", 1, 1))
    assert isinstance(validated, Err)
    assert isinstance(validated.error, InvalidVirtualMachineCreateSpec)
