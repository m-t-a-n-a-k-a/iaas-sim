from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from iaas_sim.domain.entity.virtual_machine import VirtualMachineId


@dataclass(frozen=True, slots=True)
class OperationId:
    """
    Control-plane unique identifier for an Operation.

    Distinct from backend task references (e.g., vSphere Task MOR).
    Generated as UUIDv7 at Application composition layer.
    """

    value: UUID


class OperationState(StrEnum):
    """
    Lifecycle states for asynchronous operations.

    Domain observation: OperationState tracks execution progress,
    independent of VirtualMachine.power_state (which reflects
    backend-observed VM power state).
    """

    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OperationFailure:
    """Details of a failed operation."""

    reason: str


@dataclass(frozen=True, slots=True)
class Operation:
    """
    Top-level Entity representing an asynchronous command execution.

    Invariants:
    - id: control-plane unique identity (UUIDv7)
    - target_virtual_machine_id: resource being operated on
    - action: power command (START, STOP) or future operation type
    - state: current execution state (RUNNING, SUCCEEDED, FAILED)
    - failure: populated if state == FAILED; None otherwise

    Operation lifetime spans from submission to terminal state.
    Backend task lifecycle (Task MOR, etc.) is Adapter-internal.
    """

    id: OperationId
    target_virtual_machine_id: VirtualMachineId
    action: str
    state: OperationState
    failure: OperationFailure | None = None

    def is_terminal(self) -> bool:
        """Returns True if operation reached terminal state."""
        return self.state in (OperationState.SUCCEEDED, OperationState.FAILED)


@dataclass(frozen=True, slots=True)
class VsphereTaskRef:
    """
    Internal reference to a vSphere backend Task.

    NOT exposed as public API.
    Used by Adapter to correlate Operation.id with vim.Task / MOR.
    """

    managed_object_reference: str
