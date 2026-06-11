"""健康检查快照（M4.3）—— 供 /api/health 与启动探测使用。"""

from __future__ import annotations

from typing import Any, Literal

ServiceStatus = Literal["ok", "degraded", "skipped", "starting"]

_GATEWAY_PROBE_TIMEOUT_SEC = 0.35


def _webview_service() -> dict[str, Any]:
    from friday.win10_runtime import check_webview2

    item = check_webview2()
    return {
        "status": "ok" if item.ok else "degraded",
        "detail": item.message,
        "installed": item.ok,
    }


def _gateway_port() -> int:
    import os

    raw = os.environ.get("OPENCLAW_GATEWAY_PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    from friday.edition import openclaw_gateway_port

    return openclaw_gateway_port()


def _gateway_service() -> dict[str, Any]:
    from friday.storage import load_settings
    from friday.weixin.gateway import cli_available, probe_gateway

    cfg = load_settings()
    port = _gateway_port()
    if not getattr(cfg, "weixin_bridge_enabled", True):
        return {
            "status": "skipped",
            "detail": "微信桥接已关闭",
            "running": False,
            "port": port,
            "cli_available": cli_available(),
        }

    running = probe_gateway(port=port, timeout_sec=_GATEWAY_PROBE_TIMEOUT_SEC)
    return {
        "status": "ok" if running else "degraded",
        "detail": "Gateway 运行中" if running else "Gateway 未响应",
        "running": running,
        "port": port,
        "cli_available": cli_available(),
    }


def _python_env_service() -> dict[str, Any]:
    from friday.python_env import get_setup_progress_dict, python_ready_light
    from friday.storage import load_settings, resolved_workspace

    cfg = load_settings()
    workspace = resolved_workspace(cfg)
    progress = get_setup_progress_dict()
    if progress.get("running"):
        message = str(progress.get("message") or "正在初始化 Python 环境…")
        return {
            "status": "degraded",
            "detail": message,
            "ready": False,
            "setup_running": True,
        }

    ready = python_ready_light(workspace)
    return {
        "status": "ok" if ready else "degraded",
        "detail": "已就绪" if ready else "未初始化或依赖未装全",
        "ready": ready,
        "setup_running": False,
    }


def build_health_payload(*, backend_ready: bool) -> dict[str, Any]:
    """组装 /api/health 响应；顶层 status 保持 starting|ok 以兼容现有轮询。"""
    if not backend_ready:
        return {
            "status": "starting",
            "services": {
                "backend": {"status": "starting", "detail": "启动中"},
            },
        }

    services: dict[str, dict[str, Any]] = {
        "backend": {"status": "ok", "detail": "已就绪"},
        "webview": _webview_service(),
        "gateway": _gateway_service(),
        "python_env": _python_env_service(),
    }
    degraded = any(s.get("status") == "degraded" for s in services.values())
    payload: dict[str, Any] = {
        "status": "ok",
        "services": services,
    }
    if degraded:
        payload["degraded"] = True
    return payload
