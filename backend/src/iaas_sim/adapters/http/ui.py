from __future__ import annotations

from typing import Final

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

ui_router: Final[APIRouter] = APIRouter()


@ui_router.get("/ui")
def ui_page() -> RedirectResponse:
    return RedirectResponse(url="http://localhost:4173")
