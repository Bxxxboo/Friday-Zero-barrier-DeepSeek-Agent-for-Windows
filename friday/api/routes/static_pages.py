"""静态页面与资源路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse


def register_static_routes(app: FastAPI, *, web_dir: Path) -> None:
    @app.get("/")
    async def index() -> HTMLResponse:
        html_path = web_dir / "index.html"
        html = html_path.read_text(encoding="utf-8")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    @app.get("/favicon.ico")
    async def favicon() -> FileResponse:
        from friday.paths import app_icon_path

        path = app_icon_path()
        if not path.is_file():
            raise HTTPException(status_code=404, detail="icon not found")
        return FileResponse(path, media_type="image/x-icon")
