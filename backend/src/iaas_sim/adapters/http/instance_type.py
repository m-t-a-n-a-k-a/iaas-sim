from __future__ import annotations

from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException

from iaas_sim.application.instance_type import (
    InstanceTypeNotFound,
    InstanceTypeStoreError,
    InstanceTypeStorePort,
    get_instance_type,
    list_instance_types,
)
from iaas_sim.domain.entity.instance_type import InstanceType, InstanceTypeId
from iaas_sim.result import Err, Ok

# FastAPI accesses nested route functions through decorator registration.
# pyright: reportUnusedFunction=false

UUID_VERSION_7 = 7


def instance_type_resource(instance_type: InstanceType) -> dict[str, object]:
    return {
        "id": str(instance_type.id),
        "name": instance_type.name,
        "vcpus": instance_type.vcpus,
        "memoryMiB": instance_type.memory_mib,
    }


def parse_instance_type_id(value: str) -> InstanceTypeId:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="InstanceType ID must be a UUIDv7") from exc
    if parsed.version != UUID_VERSION_7:
        raise HTTPException(status_code=422, detail="InstanceType ID must be a UUIDv7")
    return InstanceTypeId(parsed)


def _raise(error: InstanceTypeStoreError) -> NoReturn:
    if isinstance(error, InstanceTypeNotFound):
        raise HTTPException(status_code=404, detail="InstanceType not found")
    raise HTTPException(status_code=500, detail="InstanceType persistence failed")


def create_instance_type_router(store: InstanceTypeStorePort) -> APIRouter:
    router = APIRouter(prefix="/v1/instanceTypes", tags=["instanceTypes"])

    @router.get("")
    def list_resources() -> dict[str, list[dict[str, object]]]:
        match list_instance_types(store):
            case Err(error):
                _raise(error)
            case Ok(instance_types):
                return {"items": [instance_type_resource(item) for item in instance_types]}

    @router.get("/{instance_type_id}")
    def get_resource(instance_type_id: str) -> dict[str, object]:
        match get_instance_type(store, parse_instance_type_id(instance_type_id)):
            case Err(error):
                _raise(error)
            case Ok(instance_type):
                return instance_type_resource(instance_type)

    return router
