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
from iaas_sim.application.operation import (
    BackendOperationRef,
    OperationPersistenceFailure,
    OperationStorePort,
)
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
from iaas_sim.result import Err, Ok, Result, and_then, map, map_error


@dataclass(frozen=True, slots=True)
class ObservedVirtualMachine:
    backend_ref: BackendVirtualMachineRef
    name: str
    power_state: PowerState


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
        self, spec: VirtualMachineCreateSpec
    ) -> Result[BackendOperationRef, VirtualMachineCreateBackendSubmissionFailure]: ...


def _identity_error(
    error: VirtualMachineIdentityError, public_id: VirtualMachineId
) -> ApplicationError:
    if isinstance(error, VirtualMachineIdentityNotFound):
        return VirtualMachineNotFound(public_id)
    return error


def list_virtual_machines(
    port: VirtualMachinePort, identity: VirtualMachineIdentityPort
) -> Result[Sequence[VirtualMachine], ApplicationError]:
    def project_all(
        observations: Sequence[ObservedVirtualMachine],
    ) -> Result[Sequence[VirtualMachine], ApplicationError]:
        projected: list[VirtualMachine] = []
        for vm in observations:
            mapped = identity.get_or_create_by_backend_ref(vm.backend_ref)
            if isinstance(mapped, Err):
                return Err(mapped.error)
            projected.append(VirtualMachine(mapped.value, vm.name, vm.power_state))
        return Ok(tuple(projected))

    return and_then(port.list_virtual_machines(), project_all)


def get_virtual_machine(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    virtual_machine_id: VirtualMachineId,
) -> Result[VirtualMachine, ApplicationError]:
    def map_backend_error(
        error: VirtualMachineBackendNotFound | VirtualMachineBackendFailure,
    ) -> VirtualMachineNotFound | VirtualMachineBackendFailure:
        if isinstance(error, VirtualMachineBackendNotFound):
            return VirtualMachineNotFound(virtual_machine_id)
        return error

    mapped = map_error(
        identity.get_backend_ref(virtual_machine_id),
        lambda error: _identity_error(error, virtual_machine_id),
    )
    observed = and_then(
        mapped,
        lambda backend_ref: map_error(port.get_virtual_machine(backend_ref), map_backend_error),
    )
    return map(
        observed,
        lambda vm: VirtualMachine(virtual_machine_id, vm.name, vm.power_state),
    )


def execute_power_command(  # noqa: PLR0917
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    operation_id: OperationId,
    virtual_machine_id: VirtualMachineId,
    command: PowerCommand,
) -> Result[Operation, ApplicationError]:
    def observe(
        backend_ref: BackendVirtualMachineRef,
    ) -> Result[
        tuple[BackendVirtualMachineRef, AcceptedPowerCommand],
        VirtualMachineBackendNotFound | VirtualMachineBackendFailure | PowerCommandError,
    ]:
        def validate(
            observed: ObservedVirtualMachine,
        ) -> Result[tuple[BackendVirtualMachineRef, AcceptedPowerCommand], PowerCommandError]:
            validated = validate_power_command(
                VirtualMachine(virtual_machine_id, observed.name, observed.power_state), command
            )
            return map(validated, lambda accepted: (backend_ref, accepted))

        return and_then(port.get_virtual_machine(backend_ref), validate)

    def submit(
        validated: tuple[BackendVirtualMachineRef, AcceptedPowerCommand],
    ) -> Result[BackendOperationRef, PowerCommandSubmissionFailure]:
        backend_ref, accepted = validated
        return map_error(
            port.submit_power_command(backend_ref, accepted.command),
            lambda error: PowerCommandSubmissionFailure(virtual_machine_id, error.reason),
        )

    def persist(
        submitted: tuple[BackendVirtualMachineRef, AcceptedPowerCommand, BackendOperationRef],
    ) -> Result[Operation, OperationPersistenceFailure]:
        _backend_ref, accepted, task_ref = submitted
        operation = Operation(
            operation_id,
            ResourceReference("virtualMachines", str(virtual_machine_id)),
            accepted.command.value,
            Running(),
        )
        return store.create_running(operation, task_ref)

    mapped = map_error(
        identity.get_backend_ref(virtual_machine_id),
        lambda error: _identity_error(error, virtual_machine_id),
    )
    observed = map_error(
        and_then(mapped, observe),
        lambda error: (
            VirtualMachineNotFound(virtual_machine_id)
            if isinstance(error, VirtualMachineBackendNotFound)
            else error
        ),
    )
    submitted = and_then(
        observed,
        lambda value: map(submit(value), lambda task_ref: (*value, task_ref)),
    )
    return and_then(submitted, persist)


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
