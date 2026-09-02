from __future__ import annotations

from typing import NoReturn
from uuid import UUID, uuid7

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from iaas_sim.application.get_operation import get_operation as load_operation
from iaas_sim.application.identity import VirtualMachineIdentityPort
from iaas_sim.application.operation import (
    BackendOperationPort,
    OperationNotFound,
    OperationRegistryPort,
)
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
from iaas_sim.domain.entity.operation import Failed, Operation, OperationId, Running, Succeeded
from iaas_sim.domain.entity.virtual_machine import (
    AlreadyRunning,
    AlreadyStopped,
    VirtualMachine,
    VirtualMachineId,
)
from iaas_sim.result import Err, Ok

UUID_VERSION_7 = 7

# FastAPI registers nested handlers through decorators.
# pyright cannot see that registration as a function access.
# pyright: reportUnusedFunction=false


def _vm_resource(vm: VirtualMachine) -> dict[str, str]:
    return {"id": str(vm.id), "name": vm.name, "powerState": vm.power_state.value}


def operation_resource(operation: Operation) -> dict[str, object]:
    match operation.status:
        case Running():
            state, failure = "RUNNING", None
        case Succeeded():
            state, failure = "SUCCEEDED", None
        case Failed(error):
            state, failure = "FAILED", {"reason": error.reason}
    return {
        "id": str(operation.id.value),
        "target": {
            "resourceType": operation.target.resource_type,
            "id": operation.target.resource_id,
        },
        "action": operation.action,
        "state": state,
        "failure": failure,
    }


def _raise(error: ApplicationError) -> NoReturn:
    if isinstance(error, VirtualMachineNotFound):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (AlreadyRunning, AlreadyStopped)):
        raise HTTPException(status_code=409, detail=str(error))
    if isinstance(error, PowerCommandSubmissionFailure):
        raise HTTPException(status_code=502, detail=str(error))
    raise HTTPException(status_code=500, detail=str(error))


def parse_virtual_machine_id(value: str) -> VirtualMachineId:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="VirtualMachine ID must be UUIDv7") from exc
    if parsed.version != UUID_VERSION_7:
        raise HTTPException(status_code=422, detail="VirtualMachine ID must be UUIDv7")
    return VirtualMachineId(parsed)


def create_virtual_machine_router(
    port: VirtualMachinePort, identity: VirtualMachineIdentityPort, registry: OperationRegistryPort
) -> APIRouter:
    router = APIRouter(prefix="/v1/virtualMachines", tags=["virtualMachines"])

    @router.get("")
    def list_vms() -> dict[str, list[dict[str, str]]]:
        result = list_virtual_machines(port, identity)
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return {"items": [_vm_resource(vm) for vm in value]}

    @router.get("/{virtual_machine_id}")
    def get_vm(virtual_machine_id: str) -> dict[str, str]:
        result = get_virtual_machine(port, identity, parse_virtual_machine_id(virtual_machine_id))
        match result:
            case Err(error):
                _raise(error)
            case Ok(value):
                return _vm_resource(value)

    @router.post("/{virtual_machine_id}:start")
    def start_vm(virtual_machine_id: str) -> JSONResponse:
        operation_id = OperationId(uuid7())
        result = start_virtual_machine(
            port, identity, registry, operation_id, parse_virtual_machine_id(virtual_machine_id)
        )
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    content=operation_resource(operation),
                    status_code=202,
                    headers={"Location": f"/v1/operations/{operation.id.value}"},
                )

    @router.post("/{virtual_machine_id}:stop")
    def stop_vm(virtual_machine_id: str) -> JSONResponse:
        operation_id = OperationId(uuid7())
        result = stop_virtual_machine(
            port, identity, registry, operation_id, parse_virtual_machine_id(virtual_machine_id)
        )
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    content=operation_resource(operation),
                    status_code=202,
                    headers={"Location": f"/v1/operations/{operation.id.value}"},
                )

    return router


def create_operation_router(
    registry: OperationRegistryPort, backend: BackendOperationPort
) -> APIRouter:
    """Operations API: read-only endpoint for tracking async commands."""

    router = APIRouter(prefix="/v1/operations", tags=["operations"])

    @router.get("/{operation_id}")
    def get_operation(operation_id: UUID) -> dict[str, object]:
        result = load_operation(registry, backend, OperationId(operation_id))
        if isinstance(result, Err):
            if isinstance(result.error, OperationNotFound):
                raise HTTPException(status_code=404, detail=str(result.error))
            raise HTTPException(status_code=502, detail=str(result.error))
        return operation_resource(result.value)

    return router
