from __future__ import annotations

import os
from typing import Final

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from iaas_sim.adapters.http.health import create_health_router
from iaas_sim.adapters.http.instance_type import create_instance_type_router
from iaas_sim.adapters.http.openapi import openapi_router
from iaas_sim.adapters.http.snapshot import create_snapshot_router
from iaas_sim.adapters.http.ui import ui_router
from iaas_sim.adapters.http.virtual_machine import (
    create_operation_router,
    create_virtual_machine_router,
)
from iaas_sim.adapters.sqlite.adapter import SQLiteAdapter
from iaas_sim.adapters.sqlite.instance_type import SQLiteInstanceTypeStore
from iaas_sim.adapters.sqlite.migration import migrate_database
from iaas_sim.adapters.sqlite.operation import SQLiteOperationStore
from iaas_sim.adapters.sqlite.virtual_machine_create import SQLiteVirtualMachineCreateFinalizer
from iaas_sim.adapters.vsphere.adapter import VSphereAdapter
from iaas_sim.adapters.vsphere.health import vcsim_health_check
from iaas_sim.bootstrap.telemetry import configure_app_telemetry

DEFAULT_DATABASE_PATH: Final = "iaas-sim.db"

database_path = os.environ.get("IAAS_SIM_DB_PATH", DEFAULT_DATABASE_PATH)
migrate_database(database_path)

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
operation_store = SQLiteOperationStore(database_path)
instance_type_store = SQLiteInstanceTypeStore(database_path)
sqlite_adapter = SQLiteAdapter(database_path)
vm_create_finalizer = SQLiteVirtualMachineCreateFinalizer(database_path)
app.include_router(create_instance_type_router(instance_type_store))
app.include_router(
    create_virtual_machine_router(
        vsphere_adapter, sqlite_adapter, operation_store, instance_type_store
    )
)
app.include_router(create_operation_router(operation_store, vsphere_adapter, vm_create_finalizer))
app.include_router(
    create_snapshot_router(vsphere_adapter, sqlite_adapter, sqlite_adapter, operation_store)
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/openapi.json")
def openapi_json() -> dict[str, object]:
    return app.openapi()
