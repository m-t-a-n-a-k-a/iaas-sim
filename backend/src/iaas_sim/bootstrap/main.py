from __future__ import annotations

from typing import Final

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from iaas_sim.adapters.http.health import create_health_router
from iaas_sim.adapters.http.openapi import openapi_router
from iaas_sim.adapters.http.snapshot import create_snapshot_router
from iaas_sim.adapters.http.ui import ui_router
from iaas_sim.adapters.http.virtual_machine import (
    create_operation_router,
    create_virtual_machine_router,
)
from iaas_sim.adapters.memory.operation import InMemoryOperationRegistry
from iaas_sim.adapters.vsphere.adapter import VSphereAdapter
from iaas_sim.adapters.vsphere.health import vcsim_health_check
from iaas_sim.bootstrap.telemetry import configure_app_telemetry

app: Final[FastAPI] = FastAPI(
    title="iaas-sim",
    version="0.1.0",
    description="Small IaaS cloud simulator for learning and validation",
)

configure_app_telemetry(app)

app.include_router(create_health_router({"vcsim": vcsim_health_check}))
app.include_router(openapi_router)
app.include_router(ui_router)
vsphere_adapter = VSphereAdapter()
operation_registry = InMemoryOperationRegistry()
app.include_router(create_virtual_machine_router(vsphere_adapter, operation_registry))
app.include_router(create_operation_router(operation_registry, vsphere_adapter))
app.include_router(create_snapshot_router(vsphere_adapter, operation_registry))


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/openapi.json")
def openapi_json() -> dict[str, object]:
    return app.openapi()
