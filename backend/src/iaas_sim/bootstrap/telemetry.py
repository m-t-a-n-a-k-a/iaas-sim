from __future__ import annotations

from fastapi import FastAPI

from iaas_sim.adapters.telemetry.bootstrap import configure_telemetry


def configure_app_telemetry(app: FastAPI) -> None:
    configure_telemetry()
    app.state.telemetry_ready = True
