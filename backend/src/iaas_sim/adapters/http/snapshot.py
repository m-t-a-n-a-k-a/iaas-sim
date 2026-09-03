from __future__ import annotations

from typing import Literal, NoReturn
from uuid import UUID, uuid7

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from iaas_sim.adapters.http.virtual_machine import operation_resource, parse_virtual_machine_id
from iaas_sim.application.identity import (
    SnapshotIdentityPort,
    VirtualMachineIdentityNotFound,
    VirtualMachineIdentityPort,
)
from iaas_sim.application.operation import OperationPersistenceFailure, OperationStorePort
from iaas_sim.application.snapshot import (
    SnapshotApplicationError,
    SnapshotBackendFailure,
    SnapshotCommandSubmissionFailure,
    SnapshotNotFound,
    SnapshotPort,
    create_snapshot,
    delete_snapshot,
    get_snapshot,
    list_snapshots,
)
from iaas_sim.domain.entity.operation import OperationId
from iaas_sim.domain.entity.snapshot import Snapshot, SnapshotId
from iaas_sim.result import Err, Ok

# FastAPI accesses nested route functions through decorator registration.
# pyright: reportUnusedFunction=false

UUID_VERSION_7 = 7


class VirtualMachineReferenceInput(BaseModel):
    resourceType: Literal["virtualMachines"]
    id: str


class CreateSnapshotInput(BaseModel):
    name: str
    virtualMachine: VirtualMachineReferenceInput


def _snapshot_resource(snapshot: Snapshot) -> dict[str, object]:
    return {
        "id": str(snapshot.id),
        "name": snapshot.name,
        "virtualMachine": {
            "resourceType": snapshot.virtual_machine.resource_type,
            "id": snapshot.virtual_machine.resource_id,
        },
    }


def parse_snapshot_id(value: str) -> SnapshotId:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Snapshot ID must be a UUIDv7") from exc
    if parsed.version != UUID_VERSION_7:
        raise HTTPException(status_code=422, detail="Snapshot ID must be a UUIDv7")
    return SnapshotId(parsed)


def _raise(error: SnapshotApplicationError) -> NoReturn:
    if isinstance(error, OperationPersistenceFailure):
        raise HTTPException(status_code=500, detail="Operation persistence failed")
    if isinstance(error, SnapshotNotFound):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if isinstance(error, SnapshotCommandSubmissionFailure):
        detail = (
            "Snapshot creation submission failed"
            if error.operation == "create"
            else "Snapshot deletion submission failed"
        )
        raise HTTPException(status_code=502, detail=detail)
    if isinstance(error, SnapshotBackendFailure):
        raise HTTPException(status_code=502, detail="Snapshot backend request failed")
    if isinstance(error, VirtualMachineIdentityNotFound):
        raise HTTPException(status_code=404, detail="VirtualMachine not found")
    raise HTTPException(status_code=500, detail="Snapshot internal error")


def create_snapshot_router(
    port: SnapshotPort,
    vm_identity: VirtualMachineIdentityPort,
    snapshot_identity: SnapshotIdentityPort,
    store: OperationStorePort,
) -> APIRouter:
    router = APIRouter(prefix="/v1/snapshots", tags=["snapshots"])

    @router.get("")
    def list_resources() -> dict[str, list[dict[str, object]]]:
        match list_snapshots(port, vm_identity, snapshot_identity):
            case Err(error):
                _raise(error)
            case Ok(snapshots):
                return {"items": [_snapshot_resource(snapshot) for snapshot in snapshots]}

    @router.get("/{snapshot_id}")
    def get_resource(snapshot_id: str) -> dict[str, object]:
        match get_snapshot(port, vm_identity, snapshot_identity, parse_snapshot_id(snapshot_id)):
            case Err(error):
                _raise(error)
            case Ok(snapshot):
                return _snapshot_resource(snapshot)

    @router.post("")
    def create_resource(body: CreateSnapshotInput) -> JSONResponse:
        result = create_snapshot(
            port,
            vm_identity,
            store,
            OperationId(uuid7()),
            parse_virtual_machine_id(body.virtualMachine.id),
            body.name,
        )
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    operation_resource(operation),
                    202,
                    {"Location": f"/v1/operations/{operation.id}"},
                )

    @router.delete("/{snapshot_id}")
    def delete_resource(snapshot_id: str) -> JSONResponse:
        result = delete_snapshot(
            port, snapshot_identity, store, OperationId(uuid7()), parse_snapshot_id(snapshot_id)
        )
        match result:
            case Err(error):
                _raise(error)
            case Ok(operation):
                return JSONResponse(
                    operation_resource(operation),
                    202,
                    {"Location": f"/v1/operations/{operation.id}"},
                )

    return router
