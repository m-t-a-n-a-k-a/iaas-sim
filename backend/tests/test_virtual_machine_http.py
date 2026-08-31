from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iaas_sim.adapters.http.virtual_machine import create_virtual_machine_router
from iaas_sim.application.virtual_machine import (
    VirtualMachineAdapterFailure,
    VirtualMachineNotFound,
    VirtualMachineOperationFailure,
)
from iaas_sim.domain.entity.virtual_machine import PowerState, VirtualMachine, VirtualMachineId
from iaas_sim.result import Err, Ok, Result


class FakePort:
    def __init__(self) -> None:
        self.vm = VirtualMachine(VirtualMachineId("vm-1"), "demo", PowerState.STOPPED)

    def list_virtual_machines(
        self,
    ) -> Result[Sequence[VirtualMachine], VirtualMachineAdapterFailure]:
        return Ok((self.vm,))

    def get_virtual_machine(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[VirtualMachine, VirtualMachineNotFound | VirtualMachineAdapterFailure]:
        return (
            Ok(self.vm)
            if virtual_machine_id == self.vm.id
            else Err(VirtualMachineNotFound(virtual_machine_id))
        )

    def power_on(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]:
        self.vm = VirtualMachine(self.vm.id, self.vm.name, PowerState.RUNNING)
        return Ok(None)

    def power_off(
        self, virtual_machine_id: VirtualMachineId
    ) -> Result[None, VirtualMachineOperationFailure]:
        self.vm = VirtualMachine(self.vm.id, self.vm.name, PowerState.STOPPED)
        return Ok(None)


def test_virtual_machine_routes() -> None:
    expected_status_code = 200
    app = FastAPI()
    app.include_router(create_virtual_machine_router(FakePort()))
    client = TestClient(app)

    assert client.get("/v1/virtualMachines").json() == {
        "items": [{"id": "vm-1", "name": "demo", "powerState": "STOPPED"}]
    }
    assert client.get("/v1/virtualMachines/vm-1").status_code == expected_status_code
    assert client.post("/v1/virtualMachines/vm-1:start").status_code == expected_status_code
    assert client.post("/v1/virtualMachines/vm-1:stop").status_code == expected_status_code
