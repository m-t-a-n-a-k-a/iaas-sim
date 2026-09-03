from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from iaas_sim.domain.entity.instance_type import InstanceType, InstanceTypeId
from iaas_sim.result import Result


@dataclass(frozen=True, slots=True)
class InstanceTypeNotFound:
    instance_type_id: InstanceTypeId


@dataclass(frozen=True, slots=True)
class InstanceTypePersistenceFailure:
    operation: str
    reason: str


type InstanceTypeStoreError = InstanceTypeNotFound | InstanceTypePersistenceFailure


class InstanceTypeStorePort(Protocol):
    def list_instance_types(
        self,
    ) -> Result[Sequence[InstanceType], InstanceTypePersistenceFailure]: ...

    def get_instance_type(
        self, instance_type_id: InstanceTypeId
    ) -> Result[InstanceType, InstanceTypeStoreError]: ...


def list_instance_types(
    store: InstanceTypeStorePort,
) -> Result[Sequence[InstanceType], InstanceTypePersistenceFailure]:
    return store.list_instance_types()


def get_instance_type(
    store: InstanceTypeStorePort, instance_type_id: InstanceTypeId
) -> Result[InstanceType, InstanceTypeStoreError]:
    return store.get_instance_type(instance_type_id)
