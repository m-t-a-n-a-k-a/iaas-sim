from __future__ import annotations

from typing import Literal, NoReturn
from uuid import UUID, uuid7

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from iaas_sim.application.get_operation import get_operation as load_operation
from iaas_sim.application.identity import VirtualMachineIdentityPort
from iaas_sim.application.instance_type import (
    InstanceTypeNotFound,
    InstanceTypePersistenceFailure,
    InstanceTypeStorePort,
)
from iaas_sim.application.operation import (
    BackendOperationPort,
    OperationNotFound,
    OperationPersistenceFailure,
    OperationStorePort,
    VirtualMachineCreateFinalizerPort,
)
from iaas_sim.application.virtual_machine import (
    ApplicationError,
    InvalidVirtualMachineCreateSpec,
    PowerCommandSubmissionFailure,
    VirtualMachineBackendFailure,
    VirtualMachineCreateBackendSubmissionFailure,
    VirtualMachineNotFound,
    VirtualMachinePort,
    create_virtual_machine,
    get_virtual_machine,
    list_virtual_machines,
    start_virtual_machine,
    stop_virtual_machine,
)
from iaas_sim.domain.entity.instance_type import InstanceTypeId
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


class InstanceTypeReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resourceType: Literal["instanceTypes"]
    id: str


class VirtualMachineCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    instanceType: InstanceTypeReferenceRequest


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
        "id": str(operation.id),
        "target": {
            "resourceType": operation.target.resource_type,
            "id": operation.target.resource_id,
        },
        "action": operation.action,
        "state": state,
        "failure": failure,
    }


def _raise(error: ApplicationError) -> NoReturn:
    if isinstance(error, OperationPersistenceFailure):
        raise HTTPException(status_code=500, detail="Operation persistence failed")
    if isinstance(error, InstanceTypeNotFound):
        raise HTTPException(status_code=404, detail="InstanceType not found")
    if isinstance(error, InstanceTypePersistenceFailure):
        raise HTTPException(status_code=500, detail="InstanceType persistence failed")
    if isinstance(error, InvalidVirtualMachineCreateSpec):
        raise HTTPException(status_code=422, detail="Invalid VirtualMachine create request")
    if isinstance(error, VirtualMachineCreateBackendSubmissionFailure):
        raise HTTPException(status_code=502, detail="VirtualMachine creation submission failed")
    if isinstance(error, VirtualMachineNotFound):
        raise HTTPException(status_code=404, detail="VirtualMachine not found")
    if isinstance(error, (AlreadyRunning, AlreadyStopped)):
        raise HTTPException(status_code=409, detail=str(error))
    if isinstance(error, PowerCommandSubmissionFailure):
        raise HTTPException(
            status_code=502, detail="VirtualMachine power command submission failed"
        )
    if isinstance(error, VirtualMachineBackendFailure):
        raise HTTPException(status_code=502, detail="VirtualMachine backend request failed")
    raise HTTPException(status_code=500, detail="VirtualMachine internal error")


def parse_virtual_machine_id(value: str) -> VirtualMachineId:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="VirtualMachine ID must be UUIDv7") from exc
    if parsed.version != UUID_VERSION_7:
        raise HTTPException(status_code=422, detail="VirtualMachine ID must be UUIDv7")
    return VirtualMachineId(parsed)


def parse_instance_type_id(value: str) -> InstanceTypeId:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="InstanceType ID must be a UUIDv7") from exc
    if parsed.version != UUID_VERSION_7:
        raise HTTPException(status_code=422, detail="InstanceType ID must be a UUIDv7")
    return InstanceTypeId(parsed)


def create_virtual_machine_router(
    port: VirtualMachinePort,
    identity: VirtualMachineIdentityPort,
    store: OperationStorePort,
    instance_type_store: InstanceTypeStorePort | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/virtualMachines", tags=["virtualMachines"])

    @router.post("")
    def create_vm(request: VirtualMachineCreateRequest) -> JSONResponse:
        if instance_type_store is None:
            raise HTTPException(status_code=500, detail="InstanceType persistence failed")
        instance_type_id = parse_instance_type_id(request.instanceType.id)
        operation_id = OperationId(uuid7())
        virtual_machine_id = VirtualMachineId(uuid7())
        result = create_virtual_machine(
            port,
            instance_type_store,
            store,
            operation_id,
            virtual_machine_id,
            instance_type_id,
            request.name,
        )
        if isinstance(result, Err):
            _raise(result.error)
        return JSONResponse(
            content=operation_resource(result.value),
            status_code=202,
            headers={"Location": f"/v1/operations/{result.value.id}"},
        )

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
            port, identity, store, operation_id, parse_virtual_machine_id(virtual_machine_id)
        )
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    content=operation_resource(operation),
                    status_code=202,
                    headers={"Location": f"/v1/operations/{operation.id}"},
                )

    @router.post("/{virtual_machine_id}:stop")
    def stop_vm(virtual_machine_id: str) -> JSONResponse:
        operation_id = OperationId(uuid7())
        result = stop_virtual_machine(
            port, identity, store, operation_id, parse_virtual_machine_id(virtual_machine_id)
        )
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    content=operation_resource(operation),
                    status_code=202,
                    headers={"Location": f"/v1/operations/{operation.id}"},
                )

    return router


def create_operation_router(
    store: OperationStorePort,
    backend: BackendOperationPort,
    finalizer: VirtualMachineCreateFinalizerPort | None = None,
) -> APIRouter:
    """Operations API: read-only endpoint for tracking async commands."""

    router = APIRouter(prefix="/v1/operations", tags=["operations"])

    @router.get("/{operation_id}")
    def get_operation(operation_id: UUID) -> dict[str, object]:
        result = load_operation(store, backend, OperationId(operation_id), finalizer)
        if isinstance(result, Err):
            if isinstance(result.error, OperationNotFound):
                raise HTTPException(status_code=404, detail="Operation not found")
            if isinstance(result.error, OperationPersistenceFailure):
                raise HTTPException(status_code=500, detail="Operation persistence failed")
            raise HTTPException(status_code=502, detail="Operation polling failed")
        return operation_resource(result.value)

    return router
