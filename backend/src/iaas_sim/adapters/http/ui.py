from __future__ import annotations

from typing import Final

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router: Final[APIRouter] = APIRouter()


@ui_router.get("/ui")
def ui_page() -> HTMLResponse:
    html = (
        "<html>"
        "<head><title>iaas-sim console</title></head>"
        "<body>"
        '<div style="display:flex;min-height:100vh;font-family:sans-serif;">'
        '<aside style="width:220px;background:#0f172a;color:white;'
        'padding:16px;box-sizing:border-box;">'
        "<h2>iaas-sim</h2>"
        "<ul><li>Dashboard</li><li>Virtual Machines</li><li>Volumes</li>"
        "<li>Operations</li><li>Usage</li></ul>"
        "</aside>"
        '<main style="flex:1;padding:32px;background:#f8fafc;">'
        "<h1>Cloud Console</h1><p>Placeholder console for Phase 1.</p>"
        "</main></div></body></html>"
    )
    return HTMLResponse(content=html)
