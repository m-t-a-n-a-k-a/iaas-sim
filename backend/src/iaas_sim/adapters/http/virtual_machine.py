from __future__ import annotations

from collections.abc import Callable
from typing import NoReturn

from fastapi import APIRouter, HTTPException

from iaas_sim.application.virtual_machine import (
    ApplicationError,
    VirtualMachineNotFound,
    VirtualMachinePort,
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    InvalidTransition,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok, Result

# FastAPI registers nested handlers through decorators.
# pyright cannot see that registration as a function access.
# pyright: reportUnusedFunction=false


def _resource(vm: VirtualMachine) -> dict[str, str]:
    return {"id": str(vm.id), "name": vm.name, "powerState": vm.power_state.value}


def _raise(error: ApplicationError) -> NoReturn:
    if isinstance(error, VirtualMachineNotFound):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (AlreadyRunning, AlreadyStopped, InvalidTransition)):
        raise HTTPException(status_code=409, detail=str(error))
    raise HTTPException(status_code=502, detail=str(error))


def create_virtual_machine_router(port: VirtualMachinePort) -> APIRouter:
    router = APIRouter(prefix="/v1/virtualMachines", tags=["virtualMachines"])

    @router.get("")
    def list_vms() -> dict[str, list[dict[str, str]]]:
        result = list_virtual_machines(port)
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return {"items": [_resource(vm) for vm in value]}

    @router.get("/{virtual_machine_id}")
    def get_vm(virtual_machine_id: str) -> dict[str, str]:
        result = get_virtual_machine(port, VirtualMachineId(virtual_machine_id))
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return _resource(value)

    def command(
        operation: Callable[
            [VirtualMachinePort, VirtualMachineId],
            Result[VirtualMachine, ApplicationError],
        ],
        virtual_machine_id: str,
    ) -> dict[str, str]:
        result = operation(port, VirtualMachineId(virtual_machine_id))
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return _resource(value)

    @router.post("/{virtual_machine_id}:start")
    def start_vm(virtual_machine_id: str) -> dict[str, str]:
        return command(start_virtual_machine, virtual_machine_id)

    @router.post("/{virtual_machine_id}:stop")
    def stop_vm(virtual_machine_id: str) -> dict[str, str]:
        return command(stop_virtual_machine, virtual_machine_id)

    return router
