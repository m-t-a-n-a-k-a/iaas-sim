from __future__ import annotations

from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from iaas_sim.application.virtual_machine import (
    ApplicationError,
    PowerCommandSubmissionFailure,
    VirtualMachineNotFound,
    VirtualMachinePort,
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.operation import Operation, OperationId
from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok

# FastAPI registers nested handlers through decorators.
# pyright cannot see that registration as a function access.
# pyright: reportUnusedFunction=false


def _vm_resource(vm: VirtualMachine) -> dict[str, str]:
    return {"id": str(vm.id), "name": vm.name, "powerState": vm.power_state.value}


def _operation_resource(operation: Operation) -> dict[str, str | None]:
    return {
        "id": str(operation.id.value),
        "targetVirtualMachineId": str(operation.target_virtual_machine_id),
        "action": operation.action,
        "state": operation.state.value,
        "failure": operation.failure.reason if operation.failure else None,
    }


def _raise(error: ApplicationError) -> NoReturn:
    if isinstance(error, VirtualMachineNotFound):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (AlreadyRunning, AlreadyStopped)):
        raise HTTPException(status_code=409, detail=str(error))
    if isinstance(error, PowerCommandSubmissionFailure):
        raise HTTPException(status_code=502, detail=str(error))
    raise HTTPException(status_code=500, detail=str(error))


def create_virtual_machine_router(port: VirtualMachinePort) -> APIRouter:
    router = APIRouter(prefix="/v1/virtualMachines", tags=["virtualMachines"])

    @router.get("")
    def list_vms() -> dict[str, list[dict[str, str]]]:
        result = list_virtual_machines(port)
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return {"items": [_vm_resource(vm) for vm in value]}

    @router.get("/{virtual_machine_id}")
    def get_vm(virtual_machine_id: str) -> dict[str, str]:
        result = get_virtual_machine(port, VirtualMachineId(virtual_machine_id))
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return _vm_resource(value)

    @router.post("/{virtual_machine_id}:start")
    def start_vm(virtual_machine_id: str) -> JSONResponse:
        operation_id = OperationId(uuid4())
        result = start_virtual_machine(port, operation_id, VirtualMachineId(virtual_machine_id))
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    content=_operation_resource(operation),
                    status_code=202,
                    headers={"Location": f"/v1/operations/{operation.id.value}"},
                )

    @router.post("/{virtual_machine_id}:stop")
    def stop_vm(virtual_machine_id: str) -> JSONResponse:
        operation_id = OperationId(uuid4())
        result = stop_virtual_machine(port, operation_id, VirtualMachineId(virtual_machine_id))
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    content=_operation_resource(operation),
                    status_code=202,
                    headers={"Location": f"/v1/operations/{operation.id.value}"},
                )

    return router


def create_operation_router() -> APIRouter:
    """Operations API: read-only endpoint for tracking async commands."""

    router = APIRouter(prefix="/v1/operations", tags=["operations"])

    @router.get("/{operation_id}")
    def get_operation(operation_id: str) -> dict[str, str | None]:
        """
        Retrieve Operation status.

        In Phase 2A, Operations are in-memory transient.
        A real implementation would query persistent storage or
        poll backend task state.

        For now, return 404 (operations not persisted).
        """
        raise HTTPException(
            status_code=501,
            detail="Operation persistence not yet implemented in Phase 2A",
        )

    return router
