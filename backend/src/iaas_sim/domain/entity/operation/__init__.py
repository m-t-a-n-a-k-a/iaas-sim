from __future__ import annotations

from dataclasses import dataclass
from typing import NewType
from uuid import UUID

from iaas_sim.domain.resource_reference import ResourceReference

OperationId = NewType("OperationId", UUID)


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


def is_terminal(status: OperationStatus) -> bool:
    match status:
        case Running():
            return False
        case Succeeded() | Failed():
            return True
