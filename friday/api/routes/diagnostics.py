"""健康检查与诊断导出路由。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from friday.api.schemas import DiagnosticsLogsResponse


def register_diagnostics_routes(
    app: FastAPI,
    *,
    backend_ready: Callable[[], bool],
    is_local_client: Callable[[Request], bool],
) -> None:
    @app.get("/api/health")
    async def health() -> dict[str, object]:
        from friday.health_check import build_health_payload

        return await asyncio.to_thread(build_health_payload, backend_ready=backend_ready())

    @app.get("/api/auth/token")
    async def auth_token(request: Request) -> dict[str, str]:
        """供桌面端 WebView 在 token 过期时同步本地认证，仅允许本机访问。"""
        if not is_local_client(request):
            raise HTTPException(status_code=403, detail="Forbidden")
        from friday.auth import get_api_token

        return {"token": get_api_token()}

    @app.get("/api/diagnostics/logs", response_model=DiagnosticsLogsResponse)
    async def diagnostics_logs(lines: int = 30) -> DiagnosticsLogsResponse:
        from friday.logging_config import log_file_path, read_recent_log_lines

        return DiagnosticsLogsResponse(
            path=str(log_file_path()),
            lines=read_recent_log_lines(lines),
        )

    @app.get("/api/diagnostics/appdata")
    async def diagnostics_appdata() -> dict[str, str]:
        from friday.paths import get_appdata_dir

        return {"path": str(get_appdata_dir())}

    @app.post("/api/diagnostics/export")
    async def diagnostics_export() -> FileResponse:
        import tempfile
        from datetime import datetime

        from friday.diagnostics_bundle import export_diagnostic_bundle
        from friday.edition import display_version
        from friday.version import __version__

        tmp = Path(tempfile.gettempdir()) / f"friday-diagnostic-{uuid.uuid4().hex}.zip"
        path, _report = await asyncio.to_thread(export_diagnostic_bundle, tmp)
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        filename = f"Friday-diagnostic-{display_version(__version__)}-{stamp}.zip"
        return FileResponse(
            path,
            media_type="application/zip",
            filename=filename,
        )
