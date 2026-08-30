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
from iaas_sim.adapters.vsphere.health import vcsim_health_check
from iaas_sim.bootstrap.telemetry import configure_app_telemetry

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.bootstrap.main")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    try:
        vcsim_health_check()
    except Exception:
        logger.exception("startup vSphere probe failed")
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


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/openapi.json")
def openapi_json() -> dict[str, object]:
    return app.openapi()
