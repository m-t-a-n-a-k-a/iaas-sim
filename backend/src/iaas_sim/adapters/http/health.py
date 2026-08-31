from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from typing import Final
from urllib import request

from fastapi import APIRouter

from iaas_sim.result import Err, Ok, Result

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.http.health")

HealthProbe = Callable[[], object]


def create_health_router(
    probes: Mapping[str, HealthProbe] | None = None,
) -> APIRouter:
    router = APIRouter()
    probe_map = dict(probes or {})

    def _is_ok_status(check: object) -> bool:
        if not isinstance(check, dict):
            return False
        status = check.get("status")
        return isinstance(status, str) and status == "ok"

    def _probe_url(url: str) -> Result[dict[str, object], str]:
        try:
            with request.urlopen(url, timeout=5) as response:
                payload_bytes = response.read()
                payload = payload_bytes.decode("utf-8")
                if payload:
                    try:
                        details = json.loads(payload)
                        payload_result = {
                            "status": "ok",
                            "url": url,
                            "details": details,
                        }
                        return Ok(dict[str, object](payload_result))
                    except json.JSONDecodeError:
                        payload_result = {
                            "status": "ok",
                            "url": url,
                            "details": payload,
                        }
                        return Ok(dict[str, object](payload_result))
            return Ok(dict[str, object]({"status": "ok", "url": url}))
        except Exception as exc:  # pragma: no cover
            logger.exception("health probe failed for %s", url)
            return Err(f"{url}: {exc}")

    def _current_health() -> dict[str, object]:
        checks: dict[str, dict[str, object]] = {}

        for name, probe in probe_map.items():
            match probe():
                case Ok(value):
                    checks[name] = value
                case Err(error):
                    logger.warning("%s health probe failed: %s", name, error)
                    checks[name] = {"status": "error", "error": str(error)}
                case _:
                    checks[name] = {"status": "error", "error": "unknown health result"}

        dex_url = os.getenv("DEX_HEALTH_URL", "http://dex:5556/healthz")
        match _probe_url(dex_url):
            case Ok(value):
                checks["dex"] = value
            case Err(error):
                checks["dex"] = {"status": "error", "url": dex_url, "error": str(error)}

        otel_url = os.getenv("OTEL_HEALTH_URL", "http://otel-lgtm:3000/api/health")
        match _probe_url(otel_url):
            case Ok(value):
                checks["otel_lgtm"] = value
            case Err(error):
                checks["otel_lgtm"] = {"status": "error", "url": otel_url, "error": str(error)}

        overall_status = "ok" if all(_is_ok_status(check) for check in checks.values()) else "error"
        return {"status": overall_status, "checks": checks}

    def health() -> dict[str, object]:
        return _current_health()

    router.add_api_route("/health", health, methods=["GET"])
    return router


health_router: Final[APIRouter] = create_health_router()
