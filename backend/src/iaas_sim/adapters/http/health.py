from __future__ import annotations

from typing import Final

from fastapi import APIRouter

health_router: Final[APIRouter] = APIRouter()


@health_router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "checks": {
            "vcsim": "not-checked",
            "otel": "not-checked",
            "dex": "not-checked",
        },
    }
