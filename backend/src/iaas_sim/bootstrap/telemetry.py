from __future__ import annotations

from fastapi import FastAPI

from iaas_sim.adapters.telemetry.bootstrap import configure_telemetry, instrument_fastapi_app


def configure_app_telemetry(app: FastAPI) -> None:
    configure_telemetry()
    instrument_fastapi_app(app)
    app.state.telemetry_ready = True
