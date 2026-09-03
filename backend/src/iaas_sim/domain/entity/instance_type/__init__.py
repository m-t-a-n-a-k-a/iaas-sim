from dataclasses import dataclass
from typing import NewType
from uuid import UUID

InstanceTypeId = NewType("InstanceTypeId", UUID)


@dataclass(frozen=True, slots=True)
class InstanceType:
    id: InstanceTypeId
    name: str
    vcpus: int
    memory_mib: int
