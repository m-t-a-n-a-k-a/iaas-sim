# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import uuid7

import pytest

from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.application.identity import BackendVirtualMachineRef, VirtualMachineIdentityNotFound
from iaas_sim.application.operation import BackendOperationRef
from iaas_sim.application.virtual_machine import (
    ObservedVirtualMachine,
    PowerCommandBackendSubmissionFailure,
    PowerCommandSubmissionFailure,
    VirtualMachineBackendFailure,
    VirtualMachineBackendNotFound,
    VirtualMachineNotFound,
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.operation import OperationId
from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    PowerCommand,
    PowerState,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

VM_ID = VirtualMachineId(uuid7())
REF = BackendVirtualMachineRef("vm-1")


class Identity:
    def get_or_create_by_backend_ref(self, backend_ref: BackendVirtualMachineRef):
        return Ok(VM_ID)

    def get_backend_ref(self, virtual_machine_id: VirtualMachineId):
        return (
            Ok(REF)
            if virtual_machine_id == VM_ID
            else Err(VirtualMachineIdentityNotFound(virtual_machine_id))
        )


class Port:
    def __init__(self, state: PowerState):
        self.vm = ObservedVirtualMachine(REF, "demo", state)
        self.submissions = []
        self.failure = None

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[ObservedVirtualMachine], VirtualMachineBackendFailure]:
        return Ok((self.vm,))

    def get_virtual_machine(self, backend_ref: BackendVirtualMachineRef):
        if backend_ref == REF:
            return Ok(self.vm)
        return Err(VirtualMachineBackendNotFound(backend_ref))

    def submit_power_command(self, backend_ref: BackendVirtualMachineRef, command: PowerCommand):
        self.submissions.append((backend_ref, command))
        return Err(self.failure) if self.failure else Ok(BackendOperationRef("task-1"))


def test_list_and_get_project_public_identity():
    port = Port(PowerState.STOPPED)
    identity = Identity()
    assert list_virtual_machines(port, identity).value[0].id == VM_ID
    assert get_virtual_machine(port, identity, VM_ID).value.id == VM_ID


@pytest.mark.parametrize(
    ("state", "use_case", "command"),
    [
        (PowerState.STOPPED, start_virtual_machine, PowerCommand.START),
        (PowerState.RUNNING, stop_virtual_machine, PowerCommand.STOP),
    ],
)
def test_valid_command_uses_backend_ref(state, use_case, command):
    port = Port(state)
    registry = InMemoryOperationRegistry()
    result = use_case(port, Identity(), registry, OperationId(uuid7()), VM_ID)
    assert isinstance(result, Ok)
    assert result.value.target.resource_id == str(VM_ID)
    assert port.submissions == [(REF, command)]


@pytest.mark.parametrize(
    ("state", "use_case", "error"),
    [
        (PowerState.RUNNING, start_virtual_machine, AlreadyRunning(VM_ID)),
        (PowerState.STOPPED, stop_virtual_machine, AlreadyStopped(VM_ID)),
    ],
)
def test_invalid_command_has_no_side_effect(state, use_case, error):
    port = Port(state)
    result = use_case(port, Identity(), InMemoryOperationRegistry(), OperationId(uuid7()), VM_ID)
    assert result == Err(error)
    assert port.submissions == []


def test_identity_failure_has_no_backend_side_effect():
    port = Port(PowerState.STOPPED)
    unknown = VirtualMachineId(uuid7())
    assert isinstance(
        start_virtual_machine(
            port, Identity(), InMemoryOperationRegistry(), OperationId(uuid7()), unknown
        ),
        Err,
    )
    assert port.submissions == []


def test_backend_not_found_maps_to_public_identity():
    port = Port(PowerState.STOPPED)
    port.get_virtual_machine = lambda backend_ref: Err(VirtualMachineBackendNotFound(backend_ref))
    result = get_virtual_machine(port, Identity(), VM_ID)
    assert result == Err(VirtualMachineNotFound(VM_ID))
    assert "vm-1" not in str(result)


def test_power_submission_failure_maps_to_public_identity():
    port = Port(PowerState.STOPPED)
    port.failure = PowerCommandBackendSubmissionFailure(REF, "failure for vm-1")
    result = start_virtual_machine(
        port, Identity(), InMemoryOperationRegistry(), OperationId(uuid7()), VM_ID
    )
    assert result == Err(PowerCommandSubmissionFailure(VM_ID, "failure for vm-1"))
    assert result.error.virtual_machine_id == VM_ID
