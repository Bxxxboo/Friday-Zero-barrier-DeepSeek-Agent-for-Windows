from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import Future
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse

from friday.auth import ensure_api_token, get_api_token, verify_api_token

from friday.approval_narration import build_approval_user_copy, enrich_approval_summary_async
from friday.safety import PendingAction, TurnApprovalState, mark_turn_approved, should_request_approval
from friday.sessions import (
    ChatSession,
    create_session,
    delete_session,
    ensure_default_session,
    get_session,
    list_sessions,
    migrate_local_storage,
    migrate_legacy_data_dir,
    migrate_session_files,
    save_agent_state,
    session_display_messages,
    session_exists,
    set_active_session,
    rename_session,
)
from friday.operations import (
    clear_operations,
    export_operations,
    list_operations,
    replay_prompt,
)
from friday.schedules import (
    ScheduledTask,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)
from friday.skills import create_skill, delete_skill, get_skill, list_skills, list_skills_grouped, update_skill
from friday.rules import create_rule, delete_rule, ensure_builtin_rules, get_rule, list_rules, update_rule
from friday.bundled import migrate_legacy_bundled_plugins
from friday.plugins import (
    install_plugin,
    list_plugins,
    plugin_catalog,
    refresh_plugin,
    uninstall_plugin,
)
from friday.updates import check_for_updates
from friday.changelog import changelog_payload
from friday.version import __version__
from friday.paths import known_folders, web_dir
from friday.api.schemas import (
    ApprovalPayload,
    AutostartPayload,
    CancelPayload,
    ChangelogEntryResponse,
    ChangelogResponse,
    ChangelogSectionResponse,
    DiagnoseResponse,
    DiagnosticsLogsResponse,
    DisplayMessageResponse,
    GeneratedImageRef,
    LocalStorageMigrationPayload,
    MCPConfigPayload,
    MCPServerPayload,
    OperationListResponse,
    OperationResponse,
    PasteImagePayload,
    PasteImageResponse,
    PluginInstallPayload,
    PluginResponse,
    PortableExportPayload,
    PortableImportPayload,
    RulePayload,
    RuleResponse,
    RuleUpdatePayload,
    ScheduleListResponse,
    SchedulePayload,
    ScheduleResponse,
    ScheduleUpdatePayload,
    SessionCreatePayload,
    SessionDetailResponse,
    SessionListResponse,
    SessionPlanPayload,
    SessionRenamePayload,
    SessionSummaryResponse,
    SettingsPayload,
    SettingsResponse,
    SkillGroupResponse,
    SkillPayload,
    SkillResponse,
    SkillUpdatePayload,
    TestResponse,
    UpdateApplyProgressResponse,
    UpdateApplyPayload,
    UpdateApplyResponse,
    UpdateCheckResponse,
    YoloUnlockPayload,
)
from friday.storage import (
    UserSettings,
    ensure_workspace,
    initialize_first_run,
    load_settings,
    merge_settings,
    resolved_workspace,
    save_settings,
)

WEB_DIR = web_dir()

# 不在 import 时生成 token，避免 desktop 线程设置 FRIDAY_API_TOKEN 之前产生错误令牌

_backend_ready = False


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _backend_ready
    _backend_ready = False

    def _bootstrap() -> None:
        from friday.api_connect import apply_network_environment

        migrate_legacy_data_dir()
        initialize_first_run()
        apply_network_environment(load_settings())
        migrate_legacy_bundled_plugins()
        ensure_builtin_rules()
        migrate_session_files()
        ensure_default_session()
        try:
            from friday.artifacts import ensure_friday_dirs, run_gc

            cfg = load_settings()
            ensure_friday_dirs(cfg)
            run_gc(settings=cfg)
        except Exception:
            from friday.logging_config import get_logger

            get_logger("artifacts").exception("启动时生成物回收失败")

    await asyncio.to_thread(_bootstrap)
    _backend_ready = True

    async def _weixin_warmup() -> None:
        from friday.logging_config import get_logger

        try:
            if not getattr(load_settings(), "weixin_bridge_enabled", True):
                return
            port = int(os.environ.get("FRIDAY_PORT", "8765"))
            from friday.weixin.config import sync_bridge_config_from_runtime
            from friday.weixin.gateway import ensure_gateway_running_async_delay

            await asyncio.to_thread(sync_bridge_config_from_runtime)
            from friday.weixin.setup import ensure_weixin_branding
            from friday.weixin.sessions import ensure_weixin_sessions_ready

            await asyncio.to_thread(ensure_weixin_branding)
            await asyncio.to_thread(ensure_weixin_sessions_ready)
            ensure_gateway_running_async_delay(delay_sec=2.0)
        except Exception:
            get_logger("weixin").exception("微信桥接后台初始化失败")

    asyncio.create_task(_weixin_warmup())
    yield


app = FastAPI(title="Friday", lifespan=_lifespan)

from friday.api.weixin_routes import register_weixin_routes

register_weixin_routes(app)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_PUBLIC_PATHS = {"/", "/favicon.ico", "/api/health", "/api/auth/token"}
_PUBLIC_PREFIXES = ("/static/",)


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("X-Friday-Token") or request.headers.get("x-friday-token")
    if header:
        return header.strip()
    query = request.query_params.get("token")
    return query.strip() if query else None


def _is_local_client(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    if host in {"127.0.0.1", "::1", "localhost", "testclient"}:
        return True
    return host.startswith("127.")


@app.middleware("http")
async def api_token_middleware(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
        return await call_next(request)
    if path.startswith("/api/"):
        if not verify_api_token(_extract_token(request)):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized", "code": "auth_401"},
            )
    return await call_next(request)


_approval_waiters: dict[str, Future[bool]] = {}
_approval_sessions: dict[str, str] = {}
_agent_cache: dict[str, Any] = {}
_session_locks: dict[str, asyncio.Lock] = {}
_session_approval: dict[str, TurnApprovalState] = {}
_session_yolo_unlocked: set[str] = set()


def is_session_yolo_unlocked(session_id: str) -> bool:
    return bool(session_id) and session_id in _session_yolo_unlocked


def unlock_session_yolo(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    _session_yolo_unlocked.add(sid)
    return True


def lock_session_yolo(session_id: str) -> None:
    sid = (session_id or "").strip()
    if sid:
        _session_yolo_unlocked.discard(sid)


def clear_session_yolo_unlock(session_id: str | None = None) -> None:
    if session_id:
        lock_session_yolo(session_id)
    else:
        _session_yolo_unlocked.clear()


def _sync_session_approval(session_id: str, agent: Any) -> None:
    if not session_id:
        return
    if session_id in _session_approval:
        agent._turn_approval = _session_approval[session_id]
    else:
        _session_approval[session_id] = agent._turn_approval


def _save_session_approval(session_id: str, agent: Any) -> None:
    if session_id:
        _session_approval[session_id] = agent._turn_approval


def clear_session_approval(session_id: str | None = None) -> None:
    if session_id:
        _session_approval.pop(session_id, None)
        clear_session_yolo_unlock(session_id)
    else:
        _session_approval.clear()
        clear_session_yolo_unlock()


def clear_agent_cache(session_id: str | None = None) -> None:
    """清空 Agent 缓存；settings 变更后应调用。"""
    if session_id:
        _agent_cache.pop(session_id, None)
        clear_session_approval(session_id)
    else:
        _agent_cache.clear()
        clear_session_approval()


def _get_session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def _drop_session_lock(session_id: str) -> None:
    _session_locks.pop(session_id, None)


@app.get("/api/health")
async def health() -> dict[str, object]:
    from friday.health_check import build_health_payload

    return await asyncio.to_thread(build_health_payload, backend_ready=_backend_ready)


@app.get("/api/auth/token")
async def auth_token(request: Request) -> dict[str, str]:
    """供桌面端 WebView 在 token 过期时同步本地认证，仅允许本机访问。"""
    if not _is_local_client(request):
        raise HTTPException(status_code=403, detail="Forbidden")
    from friday.auth import get_api_token

    return {"token": get_api_token()}


@app.get("/api/diagnostics/logs", response_model=DiagnosticsLogsResponse)
async def diagnostics_logs(lines: int = 30) -> DiagnosticsLogsResponse:
    from friday.logging_config import log_file_path, read_recent_log_lines
    from friday.paths import get_appdata_dir

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
    from datetime import datetime, timezone

    from friday.diagnostics_bundle import export_diagnostic_bundle
    from friday.edition import display_version
    from friday.version import __version__

    tmp = Path(tempfile.gettempdir()) / f"friday-diagnostic-{uuid.uuid4().hex}.zip"
    path, _report = await asyncio.to_thread(export_diagnostic_bundle, tmp)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"Friday-diagnostic-{display_version(__version__)}-{stamp}.zip"
    return FileResponse(
        path,
        media_type="application/zip",
        filename=filename,
    )


@app.get("/")
async def index() -> HTMLResponse:
    html_path = WEB_DIR / "index.html"
    html = html_path.read_text(encoding="utf-8")
    token = get_api_token()
    inject = f'<script>window.__FRIDAY_TOKEN__="{token}";</script>'
    if "</head>" in html:
        html = html.replace("</head>", f"{inject}\n</head>", 1)
    else:
        html = inject + html
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
    return _to_response(cfg)


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
    return _to_response(merged)


@app.get("/api/autostart")
async def get_autostart() -> dict[str, object]:
    from friday.autostart import autostart_status

    return autostart_status()


@app.put("/api/autostart")
async def set_autostart(payload: AutostartPayload) -> dict[str, object]:
    from friday.autostart import set_autostart_enabled

    return set_autostart_enabled(payload.enabled)



@app.get("/api/sessions/{session_id}/plan")
async def get_session_plan_api(session_id: str) -> dict[str, Any]:
    from friday.plan import get_session_plan

    result = get_session_plan(session_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@app.put("/api/sessions/{session_id}/plan")
async def put_session_plan_api(session_id: str, payload: SessionPlanPayload) -> dict[str, Any]:
    from friday.plan import update_session_plan

    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return update_session_plan(
        session_id,
        plan_markdown=payload.plan_markdown,
        todos=payload.todos,
    )


@app.post("/api/sessions/{session_id}/plan/sync")
async def sync_session_plan_api(session_id: str) -> dict[str, Any]:
    from friday.plan import sync_todos_from_plan

    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    result = sync_todos_from_plan(session_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


@app.get("/api/mcp/servers")
async def get_mcp_servers() -> dict[str, Any]:
    from friday.mcp_client import load_mcp_config, mcp_config_path

    config = load_mcp_config()
    return {"path": str(mcp_config_path()), "servers": config.get("servers") or []}


@app.put("/api/mcp/servers")
async def put_mcp_servers(payload: MCPConfigPayload) -> dict[str, Any]:
    import uuid

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
    from pathlib import Path

    raw = str(payload.get("path", "")).strip()
    if not raw:
        raise HTTPException(status_code=400, detail="缺少 path")
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
        cfg = _merge_payload(payload)
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
            cfg = _merge_payload(payload)
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

    cfg = _merge_payload(payload)
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

    cfg = _merge_payload(payload)
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
    """开机并行检测 LLM / 视觉 / 生图（与设置页测试连接相同逻辑）。"""
    from friday.api_connect import run_startup_service_tests

    return await run_startup_service_tests()


@app.post("/api/settings/diagnose", response_model=DiagnoseResponse)
async def diagnose_settings(payload: SettingsPayload, full_api: bool = False) -> DiagnoseResponse:
    from friday.api_connect import diagnose_all

    cfg = _merge_payload(payload)
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
    report = await asyncio.to_thread(import_portable_bundle, tmp)
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    if report.get("errors"):
        raise HTTPException(status_code=400, detail="; ".join(report["errors"]))
    clear_agent_cache()
    return report


@app.post("/api/chat/paste-image", response_model=PasteImageResponse)
async def paste_chat_image(payload: PasteImagePayload) -> PasteImageResponse:
    from friday.paste_images import save_pasted_image

    cfg = load_settings()
    try:
        path, filename = await asyncio.to_thread(
            save_pasted_image,
            cfg,
            image_base64=payload.image_base64,
            data_url=payload.data_url,
            mime_type=payload.mime_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PasteImageResponse(path=path, filename=filename)


@app.get("/api/artifacts/summary")
async def api_artifacts_summary() -> dict[str, Any]:
    from friday.artifacts import storage_summary

    return await asyncio.to_thread(storage_summary)


@app.post("/api/artifacts/gc")
async def api_artifacts_gc(dry_run: bool = False) -> dict[str, Any]:
    from friday.artifacts import run_gc

    return await asyncio.to_thread(run_gc, dry_run=dry_run)


@app.get("/api/chat/generated-image")
async def get_generated_image(path: str, token: str = "", preview: int = 0) -> Response:
    from friday.auth import verify_api_token
    from friday.image_gen import guess_image_media_type, render_preview_bytes, resolve_generated_image_path

    if not verify_api_token(token):
        raise HTTPException(status_code=401, detail="未授权")
    raw = (path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="缺少 path")
    cfg = load_settings()
    try:
        target = await asyncio.to_thread(resolve_generated_image_path, raw, cfg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if preview:
        data, media_type = await asyncio.to_thread(render_preview_bytes, target)
        return Response(content=data, media_type=media_type)

    return FileResponse(target, media_type=guess_image_media_type(target))


@app.get("/api/sessions", response_model=SessionListResponse)
async def api_list_sessions() -> SessionListResponse:
    from friday.weixin.sessions import is_weixin_session

    summaries, active = list_sessions()
    if not summaries:
        session = ensure_default_session()
        summaries = [session.to_summary()]
        active = session.id
    return SessionListResponse(
        sessions=[
            SessionSummaryResponse(
                id=item.id,
                title=item.title,
                updated_at=item.updated_at,
                created_at=item.created_at,
                is_weixin=is_weixin_session(item.id),
            )
            for item in summaries
        ],
        active_session_id=active,
    )


@app.post("/api/sessions/migrate-local")
async def api_migrate_local_storage(payload: LocalStorageMigrationPayload) -> dict[str, Any]:
    if not payload.sessions:
        return {"ok": True, "imported": 0, "skipped": 0, "active_session_id": ""}
    result = migrate_local_storage(payload.sessions, payload.active_session_id.strip())
    return {"ok": True, **result}


@app.post("/api/sessions", response_model=SessionDetailResponse)
async def api_create_session(payload: SessionCreatePayload | None = None) -> SessionDetailResponse:
    title = payload.title if payload else "新对话"
    session = create_session(title=title)
    set_active_session(session.id)
    _agent_cache.pop(session.id, None)
    return _session_to_detail(session)


@app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
async def api_get_session(session_id: str) -> SessionDetailResponse:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _session_to_detail(session)


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str) -> dict[str, Any]:
    _agent_cache.pop(session_id, None)
    clear_session_approval(session_id)
    _drop_session_lock(session_id)
    next_session, next_id = delete_session(session_id)
    detail = _session_to_detail(next_session) if next_session else None
    return {"ok": True, "active_session_id": next_id, "session": detail}


@app.post("/api/sessions/{session_id}/activate")
async def api_activate_session(session_id: str) -> dict[str, Any]:
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    set_active_session(session_id)
    return {"ok": True, "active_session_id": session_id}


@app.patch("/api/sessions/{session_id}", response_model=SessionDetailResponse)
async def api_rename_session(session_id: str, payload: SessionRenamePayload) -> SessionDetailResponse:
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="名称不能为空")
    try:
        session = rename_session(session_id, title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _session_to_detail(session)


def _merge_payload(payload: SettingsPayload) -> UserSettings:
    from friday.llm_profiles import repair_llm_key_alignment

    current = load_settings()
    merged = merge_settings(current, payload.model_dump(exclude_unset=True))
    return repair_llm_key_alignment(merged)


def _to_response(cfg: UserSettings) -> SettingsResponse:
    from friday.custom_endpoints import endpoints_summary, get_active_id
    from friday.image_gen import (
        default_base_url,
        image_gen_config_hint,
        image_gen_ready,
        masked_image_gen_key,
    )
    from friday.category_profiles import category_profiles_summary
    from friday.llm_profiles import active_provider_id, llm_config_hint, profiles_summary
    from friday.custom_endpoints import active_provider_id as category_active_provider
    from friday.model_providers import infer_llm_provider, infer_vision_provider
    from friday.portability import pop_startup_notices
    from friday.vision import masked_vision_key, vision_config_hint, vision_ready

    llm_provider = active_provider_id(cfg)
    vision_provider = category_active_provider(cfg, "vision") or infer_vision_provider(cfg)

    notices = pop_startup_notices()
    autostart = {}
    try:
        from friday.autostart import autostart_status

        autostart = autostart_status()
    except Exception:
        autostart = {"enabled": False, "available": False, "detail": ""}
    return SettingsResponse(
        api_key_masked=cfg.masked_key(),
        llm_provider=llm_provider,
        llm_profiles_summary=profiles_summary(cfg),
        vision_profiles_summary=category_profiles_summary(cfg, "vision"),
        image_gen_profiles_summary=category_profiles_summary(cfg, "image_gen"),
        llm_custom_endpoints=endpoints_summary(cfg, "llm"),
        llm_custom_active=get_active_id(cfg, "llm"),
        base_url=cfg.base_url,
        model=cfg.model,
        workspace=resolved_workspace(cfg),
        api_ready=cfg.api_ready,
        llm_status_hint=llm_config_hint(cfg),
        theme=cfg.theme,
        font_size=cfg.font_size,
        restrict_to_workspace=cfg.restrict_to_workspace,
        allow_read_user_folders=getattr(cfg, "allow_read_user_folders", True),
        require_approval_writes=cfg.require_approval_writes,
        require_approval_exec=cfg.require_approval_exec,
        allow_write_files=cfg.allow_write_files,
        allow_move_files=cfg.allow_move_files,
        allow_organize=cfg.allow_organize,
        allow_create_documents=cfg.allow_create_documents,
        allow_powershell=cfg.allow_powershell,
        allow_python=cfg.allow_python,
        allow_web_browse=cfg.allow_web_browse,
        allow_downloads=cfg.allow_downloads,
        require_trusted_downloads=cfg.require_trusted_downloads,
        auto_approve_scheduled_writes=cfg.auto_approve_scheduled_writes,
        approve_once_per_turn=cfg.approve_once_per_turn,
        interaction_mode=cfg.interaction_mode,
        ui_language=getattr(cfg, "ui_language", "zh") or "zh",
        vision_api_key_masked=masked_vision_key(cfg),
        vision_provider=vision_provider,
        vision_base_url=cfg.vision_base_url,
        vision_model=cfg.vision_model,
        vision_enabled=cfg.vision_enabled,
        vision_ready=vision_ready(cfg),
        vision_status_hint=vision_config_hint(cfg),
        vision_custom_endpoints=endpoints_summary(cfg, "vision"),
        vision_custom_active=get_active_id(cfg, "vision"),
        image_gen_api_key_masked=masked_image_gen_key(cfg),
        image_gen_provider=cfg.image_gen_provider or "openai_compat",
        image_gen_base_url=cfg.image_gen_base_url.strip() or default_base_url(cfg),
        image_gen_model=cfg.image_gen_model,
        image_gen_default_size=cfg.image_gen_default_size or "1024x1024",
        image_gen_fallback_urls=cfg.image_gen_fallback_urls,
        image_gen_save_dir=cfg.image_gen_save_dir,
        image_gen_enabled=cfg.image_gen_enabled,
        image_gen_ready=image_gen_ready(cfg),
        image_gen_status_hint=image_gen_config_hint(cfg),
        image_gen_custom_endpoints=endpoints_summary(cfg, "image_gen"),
        image_gen_custom_active=get_active_id(cfg, "image_gen"),
        weixin_bridge_enabled=getattr(cfg, "weixin_bridge_enabled", True),
        acknowledged_changelog_version=getattr(cfg, "acknowledged_changelog_version", "") or "",
        portability_notices=notices,
        launch_at_logon=bool(autostart.get("enabled")),
        launch_at_logon_available=bool(autostart.get("available")),
        launch_at_logon_detail=str(autostart.get("detail") or ""),
        api_proxy=getattr(cfg, "api_proxy", "") or "",
        api_trust_env=bool(getattr(cfg, "api_trust_env", True)),
        onboarding_completed=bool(getattr(cfg, "onboarding_completed", False)),
        artifact_scratch_ttl_hours=int(getattr(cfg, "artifact_scratch_ttl_hours", 24) or 24),
        artifact_session_ttl_days=int(getattr(cfg, "artifact_session_ttl_days", 30) or 30),
        artifact_trash_ttl_days=int(getattr(cfg, "artifact_trash_ttl_days", 7) or 7),
        artifact_session_delete_grace_days=int(getattr(cfg, "artifact_session_delete_grace_days", 7) or 7),
        artifact_auto_gc_enabled=bool(getattr(cfg, "artifact_auto_gc_enabled", True)),
    )


def _session_to_detail(session: ChatSession) -> SessionDetailResponse:
    display = session_display_messages(session)
    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        updated_at=session.updated_at,
        created_at=session.created_at,
        plan_markdown=getattr(session, "plan_markdown", "") or "",
        todos=list(getattr(session, "todos", None) or []),
        messages=[
            DisplayMessageResponse(
                role=item["role"],
                content=item["content"],
                generated_images=[
                    GeneratedImageRef(path=str(img.get("path", "")))
                    for img in item.get("generated_images") or []
                    if str(img.get("path", "")).strip()
                ],
            )
            for item in display
        ],
    )


def _brain_config_changed(old: UserSettings | None, new: UserSettings) -> bool:
    if old is None:
        return True
    return (
        old.api_key != new.api_key
        or old.base_url != new.base_url
        or old.model != new.model
        or getattr(old, "api_proxy", "") != getattr(new, "api_proxy", "")
        or getattr(old, "api_trust_env", True) != getattr(new, "api_trust_env", True)
    )


def _apply_chat_settings(agent: Any, settings: UserSettings, *, yolo_unlocked: bool = False) -> None:
    from friday.api_connect import apply_network_environment, build_openai_client, invalidate_probe_cache
    from friday.brain import DeepSeekBrain

    apply_network_environment(settings)
    prev = agent.settings
    if agent.brain is None or _brain_config_changed(prev, settings):
        agent.brain = DeepSeekBrain(settings)
        invalidate_probe_cache()
    else:
        agent.brain.settings = settings
        agent.brain.client = build_openai_client(
            settings.api_key,
            settings.base_url,
            settings,
        )
    agent.refresh_prefix_if_needed(settings, yolo_unlocked=yolo_unlocked)


def _get_agent(session_id: str, settings: UserSettings, approval_bridge: Any) -> Any:
    from friday.agent import FridayAgent

    agent = _agent_cache.get(session_id)
    if agent is None:
        session = get_session(session_id)
        agent = FridayAgent(settings, approval_bridge)
        if session:
            agent.load_history(session.agent_messages)
        _agent_cache[session_id] = agent
    else:
        agent.request_approval = approval_bridge
    return agent


def _make_approval_bridge(
    loop: asyncio.AbstractEventLoop,
    emit: Any,
    session_id: str,
) -> Any:
    def approval_bridge(action: PendingAction) -> bool:
        from friday.interaction_modes import normalize_mode, tool_allowed_in_mode
        from friday.safety import ToolDecision

        agent = _agent_cache.get(session_id)
        mode_settings = agent.settings if agent else load_settings()
        mode = normalize_mode(getattr(mode_settings, "interaction_mode", "agent"))
        if not tool_allowed_in_mode(action.tool_name, mode):
            return False

        settings = mode_settings
        state = _session_approval.setdefault(session_id, TurnApprovalState())
        pseudo = ToolDecision(
            allowed=True,
            needs_approval=True,
            large_download=action.large_download,
            untrusted_download=action.untrusted_download,
        )
        if not should_request_approval(settings, pseudo, state):
            return True

        approval_id = str(uuid.uuid4())
        future: Future[bool] = Future()
        _approval_waiters[approval_id] = future
        _approval_sessions[approval_id] = session_id
        plain_summary, preview = build_approval_user_copy(action, settings=settings)
        asyncio.run_coroutine_threadsafe(
            emit(
                "approval_request",
                {
                    "approval_id": approval_id,
                    "summary": plain_summary,
                    "tool_name": action.tool_name,
                    "arguments": action.arguments,
                    "risk": action.risk.value,
                    "large_download": action.large_download,
                    "download_size_bytes": action.download_size_bytes,
                    "untrusted_download": action.untrusted_download,
                    "trust_label": action.trust_label,
                    "preview": preview,
                },
            ),
            loop,
        ).result(timeout=10.0)

        def _on_narrated(summary: str) -> None:
            if approval_id not in _approval_waiters:
                return
            asyncio.run_coroutine_threadsafe(
                emit(
                    "approval_summary_update",
                    {"approval_id": approval_id, "summary": summary},
                ),
                loop,
            )

        enrich_approval_summary_async(
            action,
            settings=settings,
            on_narrated=_on_narrated,
        )
        approved = False
        try:
            while True:
                agent = _agent_cache.get(session_id)
                if agent and agent._cancel_event.is_set():
                    return False
                try:
                    approved = future.result(timeout=0.5)
                    break
                except TimeoutError:
                    continue
        finally:
            _approval_waiters.pop(approval_id, None)
            _approval_sessions.pop(approval_id, None)

        if approved:
            mark_turn_approved(state, pseudo)
        else:
            _session_approval[session_id] = TurnApprovalState()
        return approved

    return approval_bridge


def _resolve_approval(approval_id: str, approved: bool) -> bool:
    future = _approval_waiters.pop(approval_id, None)
    _approval_sessions.pop(approval_id, None)
    if future and not future.done():
        future.set_result(approved)
        return True
    return False


def _cancel_session_approvals(session_id: str) -> None:
    for approval_id, sid in list(_approval_sessions.items()):
        if sid == session_id:
            _resolve_approval(approval_id, False)


async def _run_chat_guarded(
    session_id: str,
    text: str,
    emit: Any,
    loop: asyncio.AbstractEventLoop,
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
    interaction_mode: str = "",
) -> None:
    lock = _get_session_lock(session_id)
    if lock.locked():
        await emit("busy", {"message": "请等待当前任务完成"})
        return
    async with lock:
        await _run_chat(
            session_id,
            text,
            emit,
            loop,
            image_path=image_path,
            image_paths=image_paths,
            interaction_mode=interaction_mode,
        )


def _normalize_image_paths(image_path: str = "", image_paths: list[str] | None = None) -> list[str]:
    paths = [p.strip() for p in (image_paths or []) if (p or "").strip()]
    if not paths and (image_path or "").strip():
        paths = [image_path.strip()]
    return paths


def _compose_user_message(
    text: str,
    vision_summary: str = "",
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
) -> str:
    from friday.vision import compose_chat_message

    return compose_chat_message(
        text,
        image_path,
        vision_summary,
        image_paths=_normalize_image_paths(image_path, image_paths),
    )


async def _prefetch_vision(
    text: str,
    settings: Any,
    emit: Any,
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
) -> str:
    """粘贴截图时先发视觉 API，避免 DeepSeek 再绕一圈调工具。"""
    paths = _normalize_image_paths(image_path, image_paths)
    if not paths:
        return ""
    from friday.vision import build_vision_prompt, describe_image, vision_ready

    if not vision_ready(settings):
        return ""

    total = len(paths)
    summaries: list[str] = []
    for idx, path in enumerate(paths, start=1):
        await emit(
            "progress",
            {
                "round": 1,
                "max_rounds": 1,
                "tool_count": total,
                "tools": ["describe_image"],
                "step": idx,
            },
        )
        prompt = build_vision_prompt(text)
        part = await asyncio.to_thread(describe_image, settings, path, prompt)
        label = f"图{idx}" if total > 1 else "截图"
        summaries.append(f"【{label}】\n{part}")
    return "\n\n".join(summaries)


async def _run_chat(
    session_id: str,
    text: str,
    emit: Any,
    loop: asyncio.AbstractEventLoop,
    *,
    image_path: str = "",
    image_paths: list[str] | None = None,
    interaction_mode: str = "",
) -> None:
    from friday.interaction_modes import normalize_mode

    settings = load_settings()
    if interaction_mode:
        settings = settings.merge({"interaction_mode": normalize_mode(interaction_mode)})
    if not settings.api_ready:
        from friday.error_hints import classify_error, format_user_message

        hint = classify_error("", context="api_key_missing")
        await emit("error", {"message": format_user_message(hint)})
        return

    if not session_id or not session_exists(session_id):
        await emit("error", {"message": "会话不存在，请刷新或新建对话"})
        return

    approval_bridge = _make_approval_bridge(loop, emit, session_id)
    try:
        agent = _get_agent(session_id, settings, approval_bridge)
    except Exception as exc:
        from friday.logging_config import get_logger

        get_logger("chat").exception("Agent 初始化失败")
        from friday.api_connect import format_api_error
        from friday.model_providers import llm_service_label

        await emit(
            "error",
            {"message": format_api_error(exc, context="api_test", service=llm_service_label(settings))},
        )
        return
    yolo_unlocked = (
        normalize_mode(settings.interaction_mode) == "yolo"
        and is_session_yolo_unlocked(session_id)
    )
    _apply_chat_settings(agent, settings, yolo_unlocked=yolo_unlocked)
    _sync_session_approval(session_id, agent)
    agent.operation_meta = {
        "session_id": session_id,
        "trigger": "chat",
        "schedule_id": "",
    }
    await emit("agent_step", {"message": "正在理解你的请求…"})

    paths = _normalize_image_paths(image_path, image_paths)
    vision_summary = await _prefetch_vision(
        text,
        settings,
        emit,
        image_path=image_path,
        image_paths=paths,
    )
    user_message = _compose_user_message(
        text,
        vision_summary,
        image_path=image_path,
        image_paths=paths,
    )

    from friday.plan import plan_prompt_block

    session = get_session(session_id)
    plan_block = plan_prompt_block(session)
    if plan_block:
        user_message = f"{plan_block}\n{user_message}"

    def on_event(event_type: str, payload: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(emit(event_type, payload), loop)

    def worker() -> str:
        return agent.run(user_message, on_event=on_event)

    try:
        result = await asyncio.to_thread(worker)
        saved = save_agent_state(session_id, agent.messages, user_text=user_message)
        from friday.api_connect import record_service_status

        record_service_status("llm", settings, True, "对话成功")
        await emit(
            "assistant",
            {
                "content": result,
                "session": {
                    "id": saved.id,
                    "title": saved.title,
                    "updated_at": saved.updated_at,
                },
                "usage": agent.usage_snapshot(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        from friday.api_connect import format_api_error, is_transient_api_error, record_service_status
        from friday.model_providers import llm_service_label

        err_msg = format_api_error(
            exc, context="api_test", service=llm_service_label(settings)
        )
        record_service_status(
            "llm",
            settings,
            False,
            err_msg.split("\n")[0],
            transient=is_transient_api_error(exc),
        )
        await emit("error", {"message": err_msg})
    finally:
        _save_session_approval(session_id, agent)
        await emit("status", {"message": "就绪"})


@app.post("/api/chat/approve")
async def approve_chat(payload: ApprovalPayload) -> dict[str, bool]:
    ok = _resolve_approval(payload.approval_id, payload.approved)
    return {"ok": ok}


@app.post("/api/chat/cancel")
async def cancel_chat(payload: CancelPayload) -> dict[str, bool]:
    session_id = payload.session_id.strip()
    agent = _agent_cache.get(session_id)
    if agent:
        agent.cancel()
        _cancel_session_approvals(session_id)
        return {"ok": True}
    return {"ok": False}


@app.get("/api/runtime/status")
async def runtime_status() -> dict[str, object]:
    from friday.win10_runtime import runtime_status_payload

    return await asyncio.to_thread(runtime_status_payload)


@app.get("/api/chat/yolo-unlock/{session_id}")
async def get_yolo_unlock(session_id: str) -> dict[str, bool]:
    return {"unlocked": is_session_yolo_unlocked(session_id.strip())}


@app.post("/api/chat/yolo-unlock")
async def post_yolo_unlock(payload: YoloUnlockPayload) -> dict[str, bool]:
    session_id = payload.session_id.strip()
    if not session_id or not session_exists(session_id):
        raise HTTPException(status_code=400, detail="会话不存在")
    return {"ok": unlock_session_yolo(session_id)}


@app.delete("/api/chat/yolo-unlock/{session_id}")
async def delete_yolo_unlock(session_id: str) -> dict[str, bool]:
    lock_session_yolo(session_id.strip())
    return {"ok": True}


def _operation_to_response(item: dict[str, Any]) -> OperationResponse:
    return OperationResponse(
        id=str(item.get("id", "")),
        ts=float(item.get("ts", 0)),
        tool=str(item.get("tool", "")),
        risk=str(item.get("risk", "")),
        summary=str(item.get("summary", "")),
        args=item.get("args") or {},
        result=str(item.get("result", "")),
        success=bool(item.get("success", True)),
        session_id=str(item.get("session_id", "")),
        trigger=str(item.get("trigger", "chat")),
        schedule_id=str(item.get("schedule_id", "")),
        approved=item.get("approved"),
    )


def _schedule_to_response(task: ScheduledTask) -> ScheduleResponse:
    return ScheduleResponse(
        id=task.id,
        title=task.title,
        prompt=task.prompt,
        frequency=task.frequency,
        day_of_week=task.day_of_week,
        hour=task.hour,
        minute=task.minute,
        cron_expr=task.cron_expr,
        interval_hours=task.interval_hours,
        enabled=task.enabled,
        retry_on_failure=task.retry_on_failure,
        max_retries=task.max_retries,
        retry_count=task.retry_count,
        schedule_label=task.schedule_label(),
        last_run_at=task.last_run_at,
        next_run_at=task.next_run_at,
        last_run_status=task.last_run_status,
        last_run_message=task.last_run_message,
        created_at=task.created_at,
    )


def _skill_to_response(item: dict[str, Any]) -> SkillResponse:
    return SkillResponse(
        id=str(item.get("id", "")),
        label=str(item.get("label", "")),
        icon=str(item.get("icon", "✨")),
        category=str(item.get("category", "custom")),
        prompt=str(item.get("prompt", "")),
        builtin=bool(item.get("builtin")),
        enabled=bool(item.get("enabled", True)),
        source=str(item.get("source", "custom")),
        plugin_id=str(item.get("plugin_id", "")),
        created_at=float(item.get("created_at", 0)),
    )


def _rule_to_response(item: dict[str, Any]) -> RuleResponse:
    return RuleResponse(
        id=str(item.get("id", "")),
        title=str(item.get("title", "")),
        content=str(item.get("content", "")),
        enabled=bool(item.get("enabled", True)),
        always_apply=bool(item.get("always_apply", True)),
        source=str(item.get("source", "custom")),
        plugin_id=str(item.get("plugin_id", "")),
        created_at=float(item.get("created_at", 0)),
    )


def _plugin_to_response(item: dict[str, Any]) -> PluginResponse:
    return PluginResponse(
        id=str(item.get("id", "")),
        name=str(item.get("name", "")),
        version=str(item.get("version", "")),
        description=str(item.get("description", "")),
        author=str(item.get("author", "")),
        source=str(item.get("source", "")),
        installed_at=float(item.get("installed_at", 0)),
        updated_at=float(item.get("updated_at", 0)),
        skill_count=int(item.get("skill_count", 0)),
        rule_count=int(item.get("rule_count", 0)),
    )


@app.get("/api/operations", response_model=OperationListResponse)
async def api_list_operations(
    limit: int = 50,
    session_id: str = "",
    schedule_id: str = "",
    writes_only: bool = False,
    tool: str = "",
    risk: str = "",
    trigger: str = "",
) -> OperationListResponse:
    items = list_operations(
        limit=limit,
        session_id=session_id.strip(),
        schedule_id=schedule_id.strip(),
        writes_only=writes_only,
        tool=tool.strip(),
        risk=risk.strip(),
        trigger=trigger.strip(),
    )
    return OperationListResponse(
        operations=[_operation_to_response(item) for item in items]
    )


@app.get("/api/operations/export")
async def api_export_operations(
    format: str = "json",
    writes_only: bool = False,
    tool: str = "",
    risk: str = "",
    trigger: str = "",
    limit: int = 500,
) -> Response:
    fmt = "csv" if format.lower() == "csv" else "json"
    content, media_type, filename = export_operations(
        format=fmt,
        writes_only=writes_only,
        tool=tool.strip(),
        risk=risk.strip(),
        trigger=trigger.strip(),
        limit=limit,
    )
    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/operations/{operation_id}/replay")
async def api_replay_operation(operation_id: str) -> dict[str, Any]:
    prompt = replay_prompt(operation_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="操作记录不存在")
    return {"ok": True, "prompt": prompt}


@app.delete("/api/operations")
async def api_clear_operations() -> dict[str, Any]:
    removed = clear_operations()
    return {"ok": True, "removed": removed}


@app.get("/api/schedules", response_model=ScheduleListResponse)
async def api_list_schedules() -> ScheduleListResponse:
    tasks = list_schedules()
    return ScheduleListResponse(
        schedules=[_schedule_to_response(task) for task in tasks]
    )


@app.post("/api/schedules", response_model=ScheduleResponse)
async def api_create_schedule(payload: SchedulePayload) -> ScheduleResponse:
    title = payload.title.strip() or "未命名任务"
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写任务指令")
    task = create_schedule({
        "title": title,
        "prompt": prompt,
        "frequency": payload.frequency,
        "day_of_week": payload.day_of_week,
        "hour": payload.hour,
        "minute": payload.minute,
        "cron_expr": payload.cron_expr,
        "interval_hours": payload.interval_hours,
        "enabled": payload.enabled,
        "retry_on_failure": payload.retry_on_failure,
        "max_retries": payload.max_retries,
    })
    return _schedule_to_response(task)


@app.put("/api/schedules/{schedule_id}", response_model=ScheduleResponse)
async def api_update_schedule(
    schedule_id: str,
    payload: ScheduleUpdatePayload,
) -> ScheduleResponse:
    task = update_schedule(schedule_id, payload.model_dump(exclude_unset=True))
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _schedule_to_response(task)


@app.delete("/api/schedules/{schedule_id}")
async def api_delete_schedule(schedule_id: str) -> dict[str, bool]:
    if not delete_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@app.post("/api/schedules/{schedule_id}/run-now")
async def api_run_schedule_now(schedule_id: str) -> dict[str, Any]:
    from friday.scheduler import run_schedule_now

    if get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    status, message = await asyncio.to_thread(run_schedule_now, schedule_id)
    task = get_schedule(schedule_id)
    return {
        "ok": status == "ok",
        "status": status,
        "message": message,
        "schedule": _schedule_to_response(task).model_dump() if task else None,
    }


@app.get("/api/schedules/{schedule_id}/runs", response_model=OperationListResponse)
async def api_schedule_runs(schedule_id: str, limit: int = 30) -> OperationListResponse:
    if get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    items = list_operations(limit=limit, schedule_id=schedule_id)
    return OperationListResponse(
        operations=[_operation_to_response(item) for item in items]
    )


@app.get("/api/skills")
async def api_list_skills(
    grouped: bool = False,
    include_disabled: bool = False,
    manage: bool = False,
) -> dict[str, Any]:
    if grouped:
        groups = list_skills_grouped(include_disabled=include_disabled, for_ui=manage)
        return {
            "groups": [
                {
                    "category": g["category"],
                    "label": g["label"],
                    "skills": [_skill_to_response(s).model_dump() for s in g["skills"]],
                }
                for g in groups
            ]
        }
    return {
        "skills": [
            _skill_to_response(s).model_dump()
            for s in list_skills(include_disabled=include_disabled, for_ui=manage)
        ]
    }


@app.post("/api/skills", response_model=SkillResponse)
async def api_create_skill(payload: SkillPayload) -> SkillResponse:
    label = payload.label.strip()
    prompt = payload.prompt.strip()
    if not label:
        raise HTTPException(status_code=400, detail="请填写技能名称")
    if not prompt:
        raise HTTPException(status_code=400, detail="请填写技能指令")
    skill = create_skill(payload.model_dump())
    return _skill_to_response(skill)


@app.delete("/api/skills/{skill_id}")
async def api_delete_skill(skill_id: str) -> dict[str, bool]:
    skill = get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.get("builtin"):
        raise HTTPException(status_code=400, detail="内置技能不可删除")
    if not delete_skill(skill_id):
        raise HTTPException(status_code=404, detail="技能不存在")
    clear_agent_cache()
    return {"ok": True}


@app.put("/api/skills/{skill_id}", response_model=SkillResponse)
async def api_update_skill(skill_id: str, payload: SkillUpdatePayload) -> SkillResponse:
    skill = get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.get("builtin"):
        raise HTTPException(status_code=400, detail="内置技能不可修改")
    updated = update_skill(skill_id, payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    clear_agent_cache()
    return _skill_to_response(updated)


@app.get("/api/rules")
async def api_list_rules(manage: bool = False) -> dict[str, Any]:
    return {"rules": [_rule_to_response(r).model_dump() for r in list_rules(for_ui=manage)]}


@app.post("/api/rules", response_model=RuleResponse)
async def api_create_rule(payload: RulePayload) -> RuleResponse:
    title = payload.title.strip()
    content = payload.content.strip()
    if not title:
        raise HTTPException(status_code=400, detail="请填写规则标题")
    if not content:
        raise HTTPException(status_code=400, detail="请填写规则内容")
    rule = create_rule(payload.model_dump())
    clear_agent_cache()
    return _rule_to_response(rule)


@app.put("/api/rules/{rule_id}", response_model=RuleResponse)
async def api_update_rule(rule_id: str, payload: RuleUpdatePayload) -> RuleResponse:
    rule = update_rule(rule_id, payload.model_dump(exclude_unset=True))
    if rule is None:
        raise HTTPException(status_code=404, detail="规则不存在或不可编辑")
    clear_agent_cache()
    return _rule_to_response(rule)


@app.delete("/api/rules/{rule_id}")
async def api_delete_rule(rule_id: str) -> dict[str, bool]:
    rule = get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    if rule.get("source") == "builtin":
        raise HTTPException(status_code=400, detail="内置规则不可删除")
    if not delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="规则不存在")
    clear_agent_cache()
    return {"ok": True}


@app.get("/api/plugins/catalog")
async def api_plugin_catalog() -> dict[str, Any]:
    return {"catalog": plugin_catalog()}


@app.get("/api/plugins")
async def api_list_plugins() -> dict[str, Any]:
    return {"plugins": [_plugin_to_response(p).model_dump() for p in list_plugins()]}


@app.post("/api/plugins/install", response_model=PluginResponse)
async def api_install_plugin(payload: PluginInstallPayload) -> PluginResponse:
    source = payload.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="请填写 GitHub 仓库地址")
    try:
        entry = await asyncio.to_thread(install_plugin, source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clear_agent_cache()
    return _plugin_to_response(entry)


@app.post("/api/plugins/{plugin_id}/refresh", response_model=PluginResponse)
async def api_refresh_plugin(plugin_id: str) -> PluginResponse:
    try:
        entry = await asyncio.to_thread(refresh_plugin, plugin_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clear_agent_cache()
    return _plugin_to_response(entry)


@app.delete("/api/plugins/{plugin_id}")
async def api_uninstall_plugin(plugin_id: str) -> dict[str, bool]:
    if not uninstall_plugin(plugin_id):
        raise HTTPException(status_code=404, detail="插件不存在")
    clear_agent_cache()
    return {"ok": True}


@app.get("/api/updates/check", response_model=UpdateCheckResponse)
async def api_check_updates() -> UpdateCheckResponse:
    from friday.update_installer import can_auto_update

    info = await asyncio.to_thread(check_for_updates)
    auto_ok, auto_hint = can_auto_update()
    return UpdateCheckResponse(
        current=info.current,
        latest=info.latest,
        update_available=info.update_available,
        download_url=info.download_url,
        download_sha256=info.download_sha256,
        release_notes=info.release_notes,
        checked=info.checked,
        source_repo=info.source_repo,
        source_url=info.source_url,
        source_kind=info.source_kind,
        can_auto_update=auto_ok,
        auto_update_hint=auto_hint,
    )


@app.post("/api/updates/apply", response_model=UpdateApplyResponse)
async def api_apply_update(payload: UpdateApplyPayload) -> UpdateApplyResponse:
    from friday.update_installer import start_apply_update

    result = await asyncio.to_thread(
        start_apply_update,
        download_url=payload.download_url,
        version=payload.version,
        expected_sha256=payload.expected_sha256,
    )
    return UpdateApplyResponse(
        started=bool(result.get("started")),
        already_running=bool(result.get("already_running")),
        message=str(result.get("message") or ""),
        hint=str(result.get("hint") or ""),
    )


@app.get("/api/updates/apply/progress", response_model=UpdateApplyProgressResponse)
async def api_apply_update_progress() -> UpdateApplyProgressResponse:
    from friday.update_installer import get_apply_progress_dict

    data = await asyncio.to_thread(get_apply_progress_dict)
    return UpdateApplyProgressResponse(
        running=bool(data.get("running")),
        phase=str(data.get("phase") or "idle"),
        percent=int(data.get("percent") or 0),
        message=str(data.get("message") or ""),
        detail=str(data.get("detail") or ""),
        ok=data.get("ok") if data.get("ok") is not None else None,
        version=str(data.get("version") or ""),
        result_message=str(data.get("result_message") or ""),
        hint=str(data.get("hint") or ""),
        log=[str(x) for x in (data.get("log") or [])],
    )


def _changelog_to_response(data: dict[str, Any]) -> ChangelogResponse:
    def _map_entry(raw: dict[str, Any]) -> ChangelogEntryResponse:
        sections = []
        for sec in raw.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            items = sec.get("items") or []
            sections.append(
                ChangelogSectionResponse(
                    label=str(sec.get("label", "")),
                    items=[str(x) for x in items if x],
                )
            )
        return ChangelogEntryResponse(
            version=str(raw.get("version", "")),
            date=str(raw.get("date", "")),
            title=str(raw.get("title", "")),
            sections=sections,
        )

    return ChangelogResponse(
        current=str(data.get("current", "")),
        acknowledged=str(data.get("acknowledged", "")),
        has_unseen=bool(data.get("has_unseen")),
        entries=[_map_entry(e) for e in data.get("entries") or [] if isinstance(e, dict)],
        unseen=[_map_entry(e) for e in data.get("unseen") or [] if isinstance(e, dict)],
    )


@app.get("/api/changelog", response_model=ChangelogResponse)
async def api_changelog() -> ChangelogResponse:
    cfg = load_settings()
    ack = getattr(cfg, "acknowledged_changelog_version", "") or ""
    payload = await asyncio.to_thread(changelog_payload, ack, __version__)
    return _changelog_to_response(payload)


@app.get("/api/status-bar")
async def get_status_bar(session_id: str = "", cached_only: bool = False) -> dict[str, object]:
    from friday.status_bar import build_status_bar_snapshot

    def _usage(sid: str) -> dict[str, object]:
        if sid and sid in _agent_cache:
            return _agent_cache[sid].usage_snapshot()
        return {}

    return await build_status_bar_snapshot(
        session_id=session_id,
        cached_only=cached_only,
        session_usage=_usage,
    )


@app.get("/api/version")
async def api_version() -> dict[str, object]:
    from friday.edition import display_version
    from friday.runtime_info import runtime_info_payload
    from friday.version import GITEE_HOME, GITEE_REPO, GITHUB_HOME, GITHUB_REPO, WEBSITE_HOME

    return {
        "version": display_version(__version__),
        "gitee_home": GITEE_HOME,
        "github_home": GITHUB_HOME,
        "gitee_repo": GITEE_REPO,
        "github_repo": GITHUB_REPO,
        "website_home": WEBSITE_HOME or None,
        **await asyncio.to_thread(runtime_info_payload),
    }


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token") or websocket.headers.get("x-friday-token")
    if not verify_api_token(token):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    from friday.ws_broadcast import register_ws_client, unregister_ws_client

    async def send(event_type: str, payload: dict[str, Any] | None = None) -> None:
        body = {"type": event_type}
        if payload:
            body.update(payload)
        await websocket.send_json(body)

    register_ws_client(loop, send)
    await send("connected")

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "approval_response":
                _resolve_approval(str(data.get("approval_id", "")), bool(data.get("approved")))
                continue

            if msg_type != "chat":
                continue

            text = str(data.get("message", "")).strip()
            session_id = str(data.get("session_id", "")).strip()
            interaction_mode = str(data.get("interaction_mode", "")).strip()
            raw_paths = data.get("image_paths")
            if isinstance(raw_paths, list):
                image_paths = [str(p).strip() for p in raw_paths if str(p).strip()]
            else:
                image_paths = []
            image_path = str(data.get("image_path", "")).strip()
            if not image_paths and image_path:
                image_paths = [image_path]
            if not text and not image_paths:
                continue

            asyncio.create_task(
                _run_chat_guarded(
                    session_id,
                    text,
                    send,
                    loop,
                    image_path=image_paths[0] if len(image_paths) == 1 else "",
                    image_paths=image_paths,
                    interaction_mode=interaction_mode,
                )
            )
    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws_client(loop, send)


def find_free_port(start: int = 8765) -> int:
    """兼容旧引用；新代码请使用 friday.net.find_free_port。"""
    from friday.net import find_free_port as _find

    return _find(start)
