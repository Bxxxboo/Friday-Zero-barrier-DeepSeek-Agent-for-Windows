"""设置、环境、MCP、便携包等配置路由。"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from friday.api.chat_runtime import clear_agent_cache
from friday.api.schemas import (
    AutostartPayload,
    DiagnoseResponse,
    MCPConfigPayload,
    PortableExportPayload,
    PortableImportPayload,
    SettingsPayload,
    SettingsResponse,
    TestResponse,
    WorkspaceMemoryPayload,
)
from friday.api.settings_helpers import merge_settings_payload, settings_to_response
from friday.paths import known_folders
from friday.storage import ensure_workspace, load_settings, merge_settings, resolved_workspace, save_settings


def register_settings_routes(app: FastAPI) -> None:
    @app.get("/api/folders")
    async def api_folders() -> dict[str, Any]:
        cfg = load_settings()
        workspace = resolved_workspace(cfg)
        folders = known_folders(workspace)
        return {
            "folders": folders,
            "suggested_workspace": workspace,
        }

    @app.get("/api/settings", response_model=SettingsResponse)
    async def get_settings() -> SettingsResponse:
        cfg = load_settings()
        return settings_to_response(cfg)

    @app.get("/api/model-providers")
    async def get_model_providers() -> dict[str, object]:
        from friday.model_providers import providers_catalog

        return providers_catalog()

    @app.put("/api/settings", response_model=SettingsResponse)
    async def update_settings(payload: SettingsPayload) -> SettingsResponse:
        current = load_settings()
        merged = merge_settings(current, payload.model_dump(exclude_unset=True))
        save_settings(merged)
        from friday.api_connect import (
            apply_network_environment,
            invalidate_auth_status_for_settings_change,
            invalidate_probe_cache,
        )

        apply_network_environment(merged)
        invalidate_auth_status_for_settings_change(current, merged)
        invalidate_probe_cache(clear_auth=False)
        clear_agent_cache()
        ensure_workspace(merged)
        return settings_to_response(merged)

    @app.get("/api/autostart")
    async def get_autostart() -> dict[str, object]:
        from friday.autostart import autostart_status

        return autostart_status()

    @app.put("/api/autostart")
    async def set_autostart(payload: AutostartPayload) -> dict[str, object]:
        from friday.autostart import set_autostart_enabled

        return set_autostart_enabled(payload.enabled)

    @app.get("/api/workspace-memory")
    async def get_workspace_memory_api() -> dict[str, Any]:
        from friday.workspace_memory import load_memory

        workspace = resolved_workspace(load_settings())
        content = load_memory(workspace)
        return {"ok": True, "workspace": workspace, "content": content}

    @app.put("/api/workspace-memory")
    async def put_workspace_memory_api(payload: WorkspaceMemoryPayload) -> dict[str, Any]:
        from friday.workspace_memory import save_memory

        workspace = resolved_workspace(load_settings())
        save_memory(workspace, payload.content)
        return {"ok": True, "message": "工作区记忆已保存"}

    @app.get("/api/mcp/servers")
    async def get_mcp_servers() -> dict[str, Any]:
        from friday.mcp_client import load_mcp_config, mcp_config_path

        config = load_mcp_config()
        return {"path": str(mcp_config_path()), "servers": config.get("servers") or []}

    @app.put("/api/mcp/servers")
    async def put_mcp_servers(payload: MCPConfigPayload) -> dict[str, Any]:
        from friday.mcp_client import default_mcp_config, save_mcp_config

        servers: list[dict[str, Any]] = []
        for item in payload.servers:
            entry = item.model_dump()
            if not entry.get("id"):
                entry["id"] = uuid.uuid4().hex[:10]
            servers.append(entry)
        config = default_mcp_config()
        config["servers"] = servers
        save_mcp_config(config)
        clear_agent_cache()
        return {"ok": True, "servers": servers}

    @app.post("/api/open-path")
    async def open_path_in_explorer(payload: dict[str, Any]) -> dict[str, bool]:
        import subprocess
        import sys

        from friday.safety import path_openable_in_explorer

        raw = str(payload.get("path", "")).strip()
        if not raw:
            raise HTTPException(status_code=400, detail="缺少 path")
        cfg = load_settings()
        workspace = resolved_workspace(cfg)
        if not path_openable_in_explorer(raw, workspace, cfg):
            raise HTTPException(status_code=403, detail="路径不在允许范围内")
        target = Path(raw).expanduser().resolve()
        if sys.platform != "win32":
            return {"ok": False}
        try:
            if target.is_file():
                subprocess.run(["explorer", "/select,", str(target)], check=False)
            elif target.is_dir():
                subprocess.run(["explorer", str(target)], check=False)
            elif target.parent.exists():
                subprocess.run(["explorer", "/select,", str(target)], check=False)
            else:
                raise HTTPException(status_code=404, detail="路径不存在")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"ok": True}

    @app.get("/api/python-env")
    async def get_python_env_status() -> dict[str, object]:
        from friday.python_env import env_dict

        cfg = load_settings()
        workspace = resolved_workspace(cfg)
        return await asyncio.to_thread(env_dict, workspace)

    @app.post("/api/python-env/setup")
    async def setup_python_env() -> dict[str, object]:
        from friday.python_env import start_setup_agent_env_background

        cfg = load_settings()
        workspace = resolved_workspace(cfg)
        return await asyncio.to_thread(start_setup_agent_env_background, workspace)

    @app.get("/api/python-env/setup/progress")
    async def python_env_setup_progress() -> dict[str, object]:
        from friday.python_env import get_setup_progress_dict

        return await asyncio.to_thread(get_setup_progress_dict)

    @app.post("/api/settings/test", response_model=TestResponse)
    async def test_settings(payload: SettingsPayload) -> TestResponse:
        from friday.api_connect import test_llm_service
        from friday.error_hints import build_test_response
        from friday.logging_config import get_logger
        from friday.model_providers import llm_service_label

        log = get_logger("api")
        try:
            cfg = merge_settings_payload(payload)
            from friday.llm_profiles import llm_config_hint

            service = llm_service_label(cfg)
            config_hint = llm_config_hint(cfg)
            if config_hint:
                return TestResponse(**build_test_response(False, config_hint, service=service))
            ok, message = await asyncio.to_thread(test_llm_service, cfg)
            return TestResponse(**build_test_response(ok, message, service=service))
        except Exception as exc:
            log.exception("settings/test 未捕获异常")
            try:
                cfg = merge_settings_payload(payload)
            except Exception:
                cfg = load_settings()
            from friday.model_providers import llm_service_label

            return TestResponse(
                **build_test_response(False, str(exc), service=llm_service_label(cfg)),
            )

    @app.post("/api/settings/test-vision", response_model=TestResponse)
    async def test_vision_settings(payload: SettingsPayload) -> TestResponse:
        from friday.api_connect import test_vision_service
        from friday.error_hints import build_test_response

        cfg = merge_settings_payload(payload)
        result = await asyncio.to_thread(test_vision_service, cfg)
        if result is None:
            from friday.vision import vision_config_hint, vision_ready

            hint = vision_config_hint(cfg) or "请先勾选「启用视觉辅助」并填写 API Key"
            if not cfg.vision_enabled:
                hint = "未启用视觉辅助"
            elif not vision_ready(cfg):
                hint = vision_config_hint(cfg) or "未配置视觉 API Key"
            return TestResponse(**build_test_response(False, hint, service="视觉 API", context="vision"))
        ok, message = result
        return TestResponse(**build_test_response(ok, message, service="视觉 API", context="vision"))

    @app.post("/api/settings/test-image-gen", response_model=TestResponse)
    async def test_image_gen_settings(payload: SettingsPayload) -> TestResponse:
        from friday.api_connect import test_image_gen_service
        from friday.error_hints import build_test_response

        cfg = merge_settings_payload(payload)
        result = await asyncio.to_thread(test_image_gen_service, cfg)
        if result is None:
            hint = "请先勾选「启用生图」并填写 API Key 与模型"
            if not cfg.image_gen_enabled:
                hint = "请先勾选「启用生图」"
            return TestResponse(**build_test_response(False, hint, service="生图 API", context="image_gen"))
        ok, message = result
        return TestResponse(**build_test_response(ok, message, service="生图 API", context="image_gen"))

    @app.post("/api/settings/startup-tests")
    async def startup_api_tests() -> dict[str, object]:
        from friday.api_connect import run_startup_service_tests

        return await run_startup_service_tests()

    @app.post("/api/settings/diagnose", response_model=DiagnoseResponse)
    async def diagnose_settings(payload: SettingsPayload, full_api: bool = False) -> DiagnoseResponse:
        from friday.api_connect import diagnose_all

        cfg = merge_settings_payload(payload)
        report = await asyncio.to_thread(diagnose_all, cfg, full_api=full_api)
        return DiagnoseResponse(**report)

    @app.get("/api/portable/audit")
    async def portable_audit() -> dict[str, object]:
        from friday.portability import run_portability_audit

        cfg = load_settings()
        return {"items": run_portability_audit(cfg)}

    @app.post("/api/portable/export")
    async def portable_export(payload: PortableExportPayload | None = None) -> FileResponse:
        import tempfile

        from friday.portable_bundle import export_portable_bundle

        include_sessions = bool(payload.include_sessions) if payload else False
        tmp = Path(tempfile.gettempdir()) / f"friday-portable-{uuid.uuid4().hex}.zip"
        path, _report = await asyncio.to_thread(
            export_portable_bundle,
            tmp,
            include_sessions=include_sessions,
        )
        return FileResponse(
            path,
            media_type="application/zip",
            filename="Friday-portable.zip",
        )

    @app.post("/api/portable/import")
    async def portable_import(payload: PortableImportPayload) -> dict[str, object]:
        import base64
        import binascii
        import tempfile

        from friday.portable_bundle import import_portable_bundle

        raw = (payload.zip_base64 or "").strip()
        if not raw:
            raise HTTPException(status_code=400, detail="请上传 .zip 配置包")
        try:
            content = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="配置包数据无效") from exc
        if not content:
            raise HTTPException(status_code=400, detail="配置包为空")

        tmp = Path(tempfile.gettempdir()) / f"friday-import-{uuid.uuid4().hex}.zip"
        tmp.write_bytes(content)
        report = await asyncio.to_thread(
            import_portable_bundle,
            tmp,
            include_sessions=bool(payload.include_sessions),
        )
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        if report.get("errors"):
            raise HTTPException(status_code=400, detail="; ".join(report["errors"]))
        clear_agent_cache()
        return report
