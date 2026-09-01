from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OperationId:
    """Control-plane identity, independent of any backend operation identity."""

    value: UUID


@dataclass(frozen=True, slots=True)
class ResourceReference:
    """Minimal reference to a top-level API resource."""

    resource_type: str
    resource_id: str


@dataclass(frozen=True, slots=True)
class OperationFailure:
    reason: str


@dataclass(frozen=True, slots=True)
class Running:
    pass


@dataclass(frozen=True, slots=True)
class Succeeded:
    pass


@dataclass(frozen=True, slots=True)
class Failed:
    failure: OperationFailure


type OperationStatus = Running | Succeeded | Failed


@dataclass(frozen=True, slots=True)
class Operation:
    id: OperationId
    target: ResourceReference
    action: str
    status: OperationStatus

    def is_terminal(self) -> bool:
        return isinstance(self.status, (Succeeded, Failed))
