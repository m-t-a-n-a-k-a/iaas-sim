from dataclasses import dataclass
from typing import NewType
from uuid import UUID

from iaas_sim.domain.resource_reference import ResourceReference

SnapshotId = NewType("SnapshotId", UUID)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A backend-observed snapshot exposed as a flat top-level entity."""

    id: SnapshotId
    name: str
    virtual_machine: ResourceReference
