from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from typing import Final
from urllib import request

from fastapi import APIRouter

logger: Final[logging.Logger] = logging.getLogger("iaas_sim.http.health")

HealthProbe = Callable[[], dict[str, object]]


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

    def _probe_url(url: str) -> dict[str, object]:
        try:
            with request.urlopen(url, timeout=5) as response:
                payload_bytes = response.read()
                payload = payload_bytes.decode("utf-8")
                if payload:
                    try:
                        return {"status": "ok", "url": url, "details": json.loads(payload)}
                    except json.JSONDecodeError:
                        return {"status": "ok", "url": url, "details": payload}
            return {"status": "ok", "url": url}
        except Exception as exc:  # pragma: no cover
            logger.exception("health probe failed for %s", url)
            return {"status": "error", "url": url, "error": str(exc)}

    def _current_health() -> dict[str, object]:
        checks: dict[str, dict[str, object]] = {}

        for name, probe in probe_map.items():
            try:
                checks[name] = probe()
            except Exception as exc:  # pragma: no cover
                logger.exception("%s health probe failed", name)
                checks[name] = {"status": "error", "error": str(exc)}

        dex_url = os.getenv("DEX_HEALTH_URL", "http://dex:5556/healthz")
        checks["dex"] = _probe_url(dex_url)

        otel_url = os.getenv("OTEL_HEALTH_URL", "http://otel-lgtm:3000/api/health")
        checks["otel_lgtm"] = _probe_url(otel_url)

        overall_status = "ok" if all(_is_ok_status(check) for check in checks.values()) else "error"
        return {"status": overall_status, "checks": checks}

    def health() -> dict[str, object]:
        return _current_health()

    router.add_api_route("/health", health, methods=["GET"])
    return router


health_router: Final[APIRouter] = create_health_router()
