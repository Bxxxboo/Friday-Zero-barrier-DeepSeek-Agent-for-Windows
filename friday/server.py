from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse

from friday.auth import verify_api_token
from friday.bundled import migrate_legacy_bundled_plugins
from friday.paths import web_dir
from friday.rules import ensure_builtin_rules
from friday.sessions import ensure_default_session, migrate_legacy_data_dir, migrate_session_files
from friday.storage import initialize_first_run, load_settings

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
            from friday.history_index import ensure_schema

            ensure_schema()
        except Exception:
            from friday.logging_config import get_logger

            get_logger("history_index").exception("历史索引初始化失败")
        try:
            from friday.dream_task import run_dream_if_due

            run_dream_if_due()
        except Exception:
            from friday.logging_config import get_logger

            get_logger("dream_task").exception("Dream 任务启动失败")
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
            from friday.weixin.config import sync_bridge_config_from_runtime
            from friday.weixin.gateway import ensure_gateway_running_async_delay

            await asyncio.to_thread(sync_bridge_config_from_runtime)
            from friday.weixin.sessions import ensure_weixin_sessions_ready
            from friday.weixin.setup import ensure_weixin_branding

            await asyncio.to_thread(ensure_weixin_branding)
            await asyncio.to_thread(ensure_weixin_sessions_ready)
            ensure_gateway_running_async_delay(delay_sec=2.0)
        except Exception:
            get_logger("weixin").exception("微信桥接后台初始化失败")

    asyncio.create_task(_weixin_warmup())
    yield


app = FastAPI(title="Friday", lifespan=_lifespan)

from friday.api.routes import (  # noqa: E402
    register_chat_routes,
    register_diagnostics_routes,
    register_plugins_routes,
    register_sessions_routes,
    register_settings_routes,
    register_static_routes,
)
from friday.api.weixin_routes import register_weixin_routes  # noqa: E402

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


register_diagnostics_routes(
    app,
    backend_ready=lambda: _backend_ready,
    is_local_client=_is_local_client,
)
register_static_routes(app, web_dir=WEB_DIR)
register_settings_routes(app)
register_sessions_routes(app)
register_chat_routes(app)
register_plugins_routes(app)


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


# 向后兼容：测试与 scheduler 等仍从 friday.server 导入
from friday.api.chat_runtime import (  # noqa: E402, F401
    _agent_cache,
    clear_agent_cache,
    clear_session_approval,
    is_session_yolo_unlocked,
    unlock_session_yolo,
)
from friday.api.routes.plugins import get_status_bar  # noqa: E402, F401
from friday.api.session_helpers import _session_to_detail  # noqa: E402, F401
from friday.api.settings_helpers import _merge_payload, _to_response  # noqa: E402, F401


def find_free_port(start: int = 8765) -> int:
    """兼容旧引用；新代码请使用 friday.net.find_free_port。"""
    from friday.net import find_free_port as _find

    return _find(start)
