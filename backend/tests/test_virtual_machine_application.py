# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false
from collections.abc import Sequence
from uuid import uuid7

import pytest

import iaas_sim.application.virtual_machine as virtual_machine_application
from iaas_sim.adapters.memory.operation import InMemoryOperationStore
from iaas_sim.application.identity import (
    BackendVirtualMachineRef,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
)
from iaas_sim.application.operation import BackendOperationRef, OperationPersistenceFailure
from iaas_sim.application.virtual_machine import (
    ObservedVirtualMachine,
    PowerCommandBackendSubmissionFailure,
    PowerCommandSubmissionFailure,
    VirtualMachineBackendFailure,
    VirtualMachineBackendNotFound,
    VirtualMachineNotFound,
    execute_power_command,
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.operation import OperationId
from iaas_sim.domain.entity.virtual_machine import (
    AcceptedPowerCommand,
    AlreadyRunning,
    AlreadyStopped,
    PowerCommand,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

VM_ID = VirtualMachineId(uuid7())
REF = BackendVirtualMachineRef("vm-1")
VM_ID_2 = VirtualMachineId(uuid7())
VM_ID_3 = VirtualMachineId(uuid7())
REF_2 = BackendVirtualMachineRef("vm-2")
REF_3 = BackendVirtualMachineRef("vm-3")


class Identity:
    def find_by_backend_ref(self, backend_ref: BackendVirtualMachineRef):
        return Ok(VM_ID if backend_ref == REF else None)

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
        self.observations = []
        self.failure = None

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[ObservedVirtualMachine], VirtualMachineBackendFailure]:
        return Ok((self.vm,))

    def get_virtual_machine(self, backend_ref: BackendVirtualMachineRef):
        self.observations.append(backend_ref)
        if backend_ref == REF:
            return Ok(self.vm)
        return Err(VirtualMachineBackendNotFound(backend_ref))

    def submit_power_command(self, backend_ref: BackendVirtualMachineRef, command: PowerCommand):
        self.submissions.append((backend_ref, command))
        return Err(self.failure) if self.failure else Ok(BackendOperationRef("task-1"))


class RecordingStore(InMemoryOperationStore):
    def __init__(self, failure=None):
        super().__init__()
        self.creations = []
        self.failure = failure

    def create_running(self, operation, backend_ref):
        self.creations.append((operation, backend_ref))
        if self.failure is not None:
            return Err(self.failure)
        return super().create_running(operation, backend_ref)


class ListIdentity:
    def __init__(self, adoption_results, lookup_results):
        self.adoption_results = adoption_results
        self.lookup_results = lookup_results
        self.get_or_create_calls = []
        self.find_calls = []

    def get_or_create_by_backend_ref(self, backend_ref):
        self.get_or_create_calls.append(backend_ref)
        return self.adoption_results[backend_ref]

    def find_by_backend_ref(self, backend_ref):
        self.find_calls.append(backend_ref)
        return self.lookup_results[backend_ref]


class ListPort:
    def __init__(self, result):
        self.result = result

    def list_virtual_machines(self):
        return self.result


def test_list_and_get_project_public_identity():
    port = Port(PowerState.STOPPED)
    identity = Identity()
    assert list_virtual_machines(port, identity).value[0].id == VM_ID
    assert get_virtual_machine(port, identity, VM_ID).value.id == VM_ID


def test_list_preserves_order_while_applying_each_identity_policy() -> None:
    listed = (
        ObservedVirtualMachine(REF, "adopted", PowerState.RUNNING),
        ObservedVirtualMachine(REF_2, "exact", PowerState.STOPPED, VM_ID_2),
        ObservedVirtualMachine(REF_3, "pending", PowerState.STOPPED, VM_ID_3),
    )
    identity = ListIdentity(
        {REF: Ok(VM_ID)},
        {REF_2: Ok(VM_ID_2), REF_3: Ok(None)},
    )

    result = list_virtual_machines(ListPort(Ok(listed)), identity)

    assert result == Ok(
        (
            VirtualMachine(VM_ID, "adopted", PowerState.RUNNING),
            VirtualMachine(VM_ID_2, "exact", PowerState.STOPPED),
        )
    )
    assert identity.get_or_create_calls == [REF]
    assert identity.find_calls == [REF_2, REF_3]


@pytest.mark.parametrize(
    ("observed", "adoption_results", "lookup_results", "failure", "expected_calls"),
    [
        pytest.param(
            ObservedVirtualMachine(REF, "adoption", PowerState.STOPPED),
            {REF: Err(VirtualMachineIdentityPersistenceFailure("adopt", "unavailable"))},
            {},
            VirtualMachineIdentityPersistenceFailure("adopt", "unavailable"),
            ([REF], []),
            id="unmarked-adoption-failure",
        ),
        pytest.param(
            ObservedVirtualMachine(REF, "marked", PowerState.STOPPED, VM_ID),
            {},
            {REF: Err(VirtualMachineIdentityPersistenceFailure("find", "unavailable"))},
            VirtualMachineIdentityPersistenceFailure("find", "unavailable"),
            ([], [REF]),
            id="marked-lookup-failure",
        ),
        pytest.param(
            ObservedVirtualMachine(REF, "conflict", PowerState.STOPPED, VM_ID),
            {},
            {REF: Ok(VM_ID_2)},
            VirtualMachineIdentityPersistenceFailure(
                "list", "creation marker does not match identity mapping"
            ),
            ([], [REF]),
            id="marked-conflicting-mapping",
        ),
    ],
)
def test_list_returns_exact_identity_policy_failure(
    observed, adoption_results, lookup_results, failure, expected_calls
) -> None:
    identity = ListIdentity(adoption_results, lookup_results)

    result = list_virtual_machines(ListPort(Ok((observed,))), identity)

    assert result == Err(failure)
    assert (identity.get_or_create_calls, identity.find_calls) == expected_calls


def test_list_backend_failure_does_not_resolve_identities() -> None:
    failure = VirtualMachineBackendFailure("list", "backend unavailable")
    identity = ListIdentity({}, {})

    result = list_virtual_machines(ListPort(Err(failure)), identity)

    assert result == Err(failure)
    assert identity.get_or_create_calls == []
    assert identity.find_calls == []


@pytest.mark.parametrize(
    ("state", "use_case", "command"),
    [
        (PowerState.STOPPED, start_virtual_machine, PowerCommand.START),
        (PowerState.RUNNING, stop_virtual_machine, PowerCommand.STOP),
    ],
)
def test_valid_command_uses_backend_ref(state, use_case, command):
    port = Port(state)
    registry = InMemoryOperationStore()
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
    result = use_case(port, Identity(), InMemoryOperationStore(), OperationId(uuid7()), VM_ID)
    assert result == Err(error)
    assert port.submissions == []


def test_identity_failure_has_no_backend_side_effect():
    port = Port(PowerState.STOPPED)
    store = RecordingStore()
    unknown = VirtualMachineId(uuid7())
    assert isinstance(
        start_virtual_machine(port, Identity(), store, OperationId(uuid7()), unknown),
        Err,
    )
    assert port.submissions == []
    assert port.observations == []
    assert store.creations == []


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
        port, Identity(), InMemoryOperationStore(), OperationId(uuid7()), VM_ID
    )
    assert result == Err(PowerCommandSubmissionFailure(VM_ID, "failure for vm-1"))
    assert result.error.virtual_machine_id == VM_ID


def test_power_pipeline_passes_validated_command_to_later_stages(monkeypatch) -> None:
    port = Port(PowerState.STOPPED)
    monkeypatch.setattr(
        virtual_machine_application,
        "validate_power_command",
        lambda vm, command: Ok(AcceptedPowerCommand(vm.id, PowerCommand.STOP)),
    )

    result = start_virtual_machine(
        port, Identity(), InMemoryOperationStore(), OperationId(uuid7()), VM_ID
    )

    assert isinstance(result, Ok)
    assert port.submissions == [(REF, PowerCommand.STOP)]
    assert result.value.action == PowerCommand.STOP.value


def test_power_workflow_observation_failure_stops_submission_and_persistence() -> None:
    port = Port(PowerState.STOPPED)
    port.get_virtual_machine = lambda backend_ref: Err(VirtualMachineBackendNotFound(backend_ref))
    store = RecordingStore()

    result = execute_power_command(
        port, Identity(), store, OperationId(uuid7()), VM_ID, PowerCommand.START
    )

    assert result == Err(VirtualMachineNotFound(VM_ID))
    assert port.submissions == []
    assert store.creations == []


def test_power_workflow_validation_failure_stops_submission_and_persistence() -> None:
    port = Port(PowerState.RUNNING)
    store = RecordingStore()

    result = execute_power_command(
        port, Identity(), store, OperationId(uuid7()), VM_ID, PowerCommand.START
    )

    assert result == Err(AlreadyRunning(VM_ID))
    assert port.submissions == []
    assert store.creations == []


def test_power_workflow_submission_failure_stops_persistence() -> None:
    port = Port(PowerState.STOPPED)
    port.failure = PowerCommandBackendSubmissionFailure(REF, "submission failed")
    store = RecordingStore()

    result = execute_power_command(
        port, Identity(), store, OperationId(uuid7()), VM_ID, PowerCommand.START
    )

    assert result == Err(PowerCommandSubmissionFailure(VM_ID, "submission failed"))
    assert store.creations == []


def test_power_workflow_returns_exact_persistence_failure() -> None:
    failure = OperationPersistenceFailure("create", "database unavailable")
    store = RecordingStore(failure)

    result = execute_power_command(
        Port(PowerState.STOPPED),
        Identity(),
        store,
        OperationId(uuid7()),
        VM_ID,
        PowerCommand.START,
    )

    assert result == Err(failure)
