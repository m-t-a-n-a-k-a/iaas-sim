from dataclasses import dataclass
from typing import NewType

from iaas_sim.domain.resource_reference import ResourceReference

SnapshotId = NewType("SnapshotId", str)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A backend-observed snapshot exposed as a flat top-level entity."""

    id: SnapshotId
    name: str
    virtual_machine: ResourceReference
