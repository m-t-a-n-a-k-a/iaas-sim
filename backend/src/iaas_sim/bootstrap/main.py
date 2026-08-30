from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import Final

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from iaas_sim.adapters.http.health import health_router
from iaas_sim.adapters.http.openapi import openapi_router
from iaas_sim.adapters.http.ui import ui_router
from iaas_sim.adapters.vsphere.health import vcsim_health_check


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    with suppress(Exception):
        vcsim_health_check()
    yield


app: Final[FastAPI] = FastAPI(
    title="iaas-sim",
    version="0.1.0",
    description="Small IaaS cloud simulator for learning and validation",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(openapi_router)
app.include_router(ui_router)


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return "<html><body><h1>iaas-sim placeholder</h1></body></html>"


@app.get("/openapi.json")
def openapi_json() -> dict[str, object]:
    return app.openapi()
