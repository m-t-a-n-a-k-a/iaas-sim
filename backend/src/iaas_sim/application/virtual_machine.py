from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.application.identity import (
    BackendVirtualMachineRef,
    VirtualMachineIdentityError,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPersistenceFailure,
    VirtualMachineIdentityPort,
)
from iaas_sim.application.instance_type import (
    InstanceTypeNotFound,
    InstanceTypePersistenceFailure,
    InstanceTypeStorePort,
)
from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationPersistenceFailure,
    OperationStorePort,
)
from iaas_sim.domain.entity.instance_type import InstanceTypeId
from iaas_sim.domain.entity.operation import Operation, OperationId, Running
from iaas_sim.domain.entity.virtual_machine import (
    AcceptedPowerCommand,
    PowerCommand,
    PowerCommandError,
    PowerState,
    VirtualMachine,
    VirtualMachineId,
    validate_power_command,
)
from iaas_sim.domain.resource_reference import ResourceReference
from iaas_sim.result import Err, Ok, Result, ResultUnwrapper, result_workflow


@dataclass(frozen=True, slots=True)
class ObservedVirtualMachine:
    backend_ref: BackendVirtualMachineRef
    name: str
    power_state: PowerState
    creation_virtual_machine_id: VirtualMachineId | None = None


@dataclass(frozen=True, slots=True)
class VirtualMachineNotFound:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class VirtualMachineBackendNotFound:
    backend_ref: BackendVirtualMachineRef


@dataclass(frozen=True, slots=True)
class VirtualMachineBackendFailure:
    operation: str
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandSubmissionFailure:
    virtual_machine_id: VirtualMachineId
    reason: str


@dataclass(frozen=True, slots=True)
class PowerCommandBackendSubmissionFailure:
    backend_ref: BackendVirtualMachineRef
    reason: str


@dataclass(frozen=True, slots=True)
class VirtualMachineCreateSpec:
    """Resolved, backend-independent inputs for creating a blank VM."""

    name: str
    vcpus: int
    memory_mib: int


@dataclass(frozen=True, slots=True)
class InvalidVirtualMachineCreateSpec:
    reason: str


@dataclass(frozen=True, slots=True)
class VirtualMachineCreateBackendSubmissionFailure:
    reason: str


def validate_virtual_machine_create_spec(
    spec: VirtualMachineCreateSpec,
) -> Result[VirtualMachineCreateSpec, InvalidVirtualMachineCreateSpec]:
    """Apply only the backend-independent minimum required create validation."""
    if spec.name == "":
        return Err(InvalidVirtualMachineCreateSpec("name must not be empty"))
    if spec.vcpus <= 0 or spec.memory_mib <= 0:
        return Err(InvalidVirtualMachineCreateSpec("sizing must be positive"))
    return Ok(spec)


type ApplicationError = (
    VirtualMachineNotFound
    | VirtualMachineBackendFailure
    | VirtualMachineIdentityPersistenceFailure
    | PowerCommandError
    | PowerCommandSubmissionFailure
    | OperationPersistenceFailure
    | InstanceTypeNotFound
    | InstanceTypePersistenceFailure
    | InvalidVirtualMachineCreateSpec
    | VirtualMachineCreateBackendSubmissionFailure
)


class VirtualMachinePort(Protocol):
    def list_virtual_machines(
        self,
    ) -> Result[Sequence[ObservedVirtualMachine], VirtualMachineBackendFailure]: ...
    def get_virtual_machine(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[
        ObservedVirtualMachine, VirtualMachineBackendNotFound | VirtualMachineBackendFailure
    ]: ...
    def submit_power_command(
        self, backend_ref: BackendVirtualMachineRef, command: PowerCommand
    ) -> Result[BackendOperationRef, PowerCommandBackendSubmissionFailure]: ...
    def submit_create_virtual_machine(
        self, virtual_machine_id: VirtualMachineId, spec: VirtualMachineCreateSpec
    ) -> Result[BackendOperationRef, VirtualMachineCreateBackendSubmissionFailure]: ...


def _identity_error(
    error: VirtualMachineIdentityError, public_id: VirtualMachineId
) -> ApplicationError:
    if isinstance(error, VirtualMachineIdentityNotFound):
        return VirtualMachineNotFound(public_id)
    return error


def _observation_error(
    error: VirtualMachineBackendNotFound | VirtualMachineBackendFailure,
    public_id: VirtualMachineId,
) -> ApplicationError:
    if isinstance(error, VirtualMachineBackendNotFound):
        return VirtualMachineNotFound(public_id)
    return error


def _submission_error(
    error: PowerCommandBackendSubmissionFailure, public_id: VirtualMachineId
) -> ApplicationError:
    return PowerCommandSubmissionFailure(public_id, error.reason)


def _as_application_error(error: ApplicationError) -> ApplicationError:
    return error


def _resolve_listed_virtual_machine_id(
    vm: ObservedVirtualMachine, identity: VirtualMachineIdentityPort
) -> Result[VirtualMachineId | None, ApplicationError]:
    marker = vm.creation_virtual_machine_id
    if marker is None:
        mapped = identity.get_or_create_by_backend_ref(vm.backend_ref)
        if isinstance(mapped, Err):
            return Err[ApplicationError](mapped.error)
        return Ok(mapped.value)

    existing = identity.find_by_backend_ref(vm.backend_ref)
    if isinstance(existing, Err):
        return Err[ApplicationError](existing.error)
    if existing.value is None:
        return Ok(None)
    if existing.value != marker:
        return Err[ApplicationError](
            VirtualMachineIdentityPersistenceFailure(
                "list", "creation marker does not match identity mapping"
            )
        )
    return Ok(existing.value)


@result_workflow
def list_virtual_machines(
    unwrap: ResultUnwrapper[ApplicationError],
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
) -> Sequence[VirtualMachine]:
    listed = unwrap.map_error(port.list_virtual_machines(), _as_application_error)

    projected: list[VirtualMachine] = []
    for vm in listed:
        public_id = unwrap(_resolve_listed_virtual_machine_id(vm, identity))
        if public_id is None:
            continue
        projected.append(VirtualMachine(public_id, vm.name, vm.power_state))
    return tuple(projected)


@result_workflow
def get_virtual_machine(
    unwrap: ResultUnwrapper[ApplicationError],
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    virtual_machine_id: VirtualMachineId,
) -> VirtualMachine:
    backend_ref = unwrap.map_error(
        identity.get_backend_ref(virtual_machine_id),
        lambda error: _identity_error(error, virtual_machine_id),
    )
    observed = unwrap.map_error(
        port.get_virtual_machine(backend_ref),
        lambda error: _observation_error(error, virtual_machine_id),
    )

    marker = observed.creation_virtual_machine_id
    if marker is not None and marker != virtual_machine_id:
        return unwrap(
            Err[ApplicationError](
                VirtualMachineIdentityPersistenceFailure(
                    "get", "creation marker does not match requested identity"
                )
            )
        )
    return VirtualMachine(virtual_machine_id, observed.name, observed.power_state)


def create_virtual_machine(  # noqa: PLR0917
    port: VirtualMachinePort,
    instance_type_store: InstanceTypeStorePort,
    operation_store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    instance_type_id: InstanceTypeId,
    name: str,
) -> Result[Operation, ApplicationError]:
    resolved = instance_type_store.get_instance_type(instance_type_id)
    if isinstance(resolved, Err):
        return Err[ApplicationError](resolved.error)

    validated = validate_virtual_machine_create_spec(
        VirtualMachineCreateSpec(name, resolved.value.vcpus, resolved.value.memory_mib)
    )
    if isinstance(validated, Err):
        return Err[ApplicationError](validated.error)

    submitted = port.submit_create_virtual_machine(virtual_machine_id, validated.value)
    if isinstance(submitted, Err):
        return Err[ApplicationError](submitted.error)

    operation = Operation(
        operation_id,
        ResourceReference("virtualMachines", str(virtual_machine_id)),
        "CREATE",
        Running(),
    )
    persisted = operation_store.create_running(operation, submitted.value)
    if isinstance(persisted, Err):
        return Err[ApplicationError](persisted.error)
    return persisted


@result_workflow
def execute_power_command(  # noqa: PLR0917
    unwrap: ResultUnwrapper[ApplicationError],
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    command: PowerCommand,
) -> Operation:
    backend_ref = unwrap.map_error(
        identity.get_backend_ref(virtual_machine_id),
        lambda error: _identity_error(error, virtual_machine_id),
    )
    observed = unwrap.map_error(
        port.get_virtual_machine(backend_ref),
        lambda error: _observation_error(error, virtual_machine_id),
    )
    accepted: AcceptedPowerCommand = unwrap.map_error(
        validate_power_command(
            VirtualMachine(
                virtual_machine_id,
                observed.name,
                observed.power_state,
            ),
            command,
        ),
        _as_application_error,
    )
    backend_operation_ref = unwrap.map_error(
        port.submit_power_command(backend_ref, accepted.command),
        lambda error: _submission_error(error, virtual_machine_id),
    )
    operation = Operation(
        operation_id,
        ResourceReference("virtualMachines", str(virtual_machine_id)),
        accepted.command.value,
        Running(),
    )
    return unwrap.map_error(
        store.create_running(operation, backend_operation_ref),
        _as_application_error,
    )


def start_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, identity, store, operation_id, virtual_machine_id, PowerCommand.START
    )


def stop_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
) -> Result[Operation, ApplicationError]:
    return execute_power_command(
        port, identity, store, operation_id, virtual_machine_id, PowerCommand.STOP
    )
