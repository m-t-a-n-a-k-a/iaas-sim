from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, Protocol

from iaas_sim.domain.entity.virtual_machine import VirtualMachineId
from iaas_sim.result import Result

BackendVirtualMachineRef = NewType("BackendVirtualMachineRef", str)


@dataclass(frozen=True, slots=True)
class VirtualMachineIdentityNotFound:
    virtual_machine_id: VirtualMachineId


@dataclass(frozen=True, slots=True)
class VirtualMachineIdentityPersistenceFailure:
    operation: str
    reason: str


type VirtualMachineIdentityError = (
    VirtualMachineIdentityNotFound | VirtualMachineIdentityPersistenceFailure
)


class VirtualMachineIdentityPort(Protocol):
    def get_or_create_by_backend_ref(
        self, backend_ref: BackendVirtualMachineRef
    ) -> Result[VirtualMachineId, VirtualMachineIdentityPersistenceFailure]: ...

    def get_backend_ref(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[BackendVirtualMachineRef, VirtualMachineIdentityError]: ...
