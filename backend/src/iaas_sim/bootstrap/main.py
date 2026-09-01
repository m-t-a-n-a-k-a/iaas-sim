from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from iaas_sim.adapters.http.health import create_health_router
from iaas_sim.adapters.http.openapi import openapi_router
from iaas_sim.adapters.http.ui import ui_router
from iaas_sim.adapters.http.virtual_machine import (
    create_operation_router,
    create_virtual_machine_router,
)
from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.adapters.vsphere.health import vcsim_health_check
from iaas_sim.adapters.vsphere.virtual_machine import VSphereVirtualMachineAdapter
from iaas_sim.bootstrap.telemetry import configure_app_telemetry
from iaas_sim.result import Err, Ok

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.bootstrap.main")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    match vcsim_health_check():
        case Ok(value):
            logger.info("startup vSphere probe succeeded: %s", value.get("virtual_machine_count"))
        case Err(error):
            logger.warning("startup vSphere probe failed: %s", error)
    yield


app: Final[FastAPI] = FastAPI(
    title="iaas-sim",
    version="0.1.0",
    description="Small IaaS cloud simulator for learning and validation",
    lifespan=lifespan,
)

configure_app_telemetry(app)

app.include_router(create_health_router({"vcsim": vcsim_health_check}))
app.include_router(openapi_router)
app.include_router(ui_router)
vsphere_adapter = VSphereVirtualMachineAdapter()
operation_registry = InMemoryOperationRegistry()
app.include_router(create_virtual_machine_router(vsphere_adapter, operation_registry))
app.include_router(create_operation_router(operation_registry, vsphere_adapter))


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/openapi.json")
def openapi_json() -> dict[str, object]:
    return app.openapi()
