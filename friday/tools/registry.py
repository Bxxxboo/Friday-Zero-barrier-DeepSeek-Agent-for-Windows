"""工具注册中心 —— 通过装饰器自动收集，无需手动维护定义和映射列表。

轻量工具模块启动时加载；documents / media 延迟 import，加快冷启动。
"""

from __future__ import annotations

import importlib
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from friday.config import (
    CANCEL_POLL_INTERVAL,
    TOOL_TIMEOUT_DOWNLOAD,
    TOOL_TIMEOUT_DOWNLOAD_LARGE,
    TOOL_TIMEOUT_EXEC,
    TOOL_TIMEOUT_READ,
    TOOL_TIMEOUT_VISION,
    TOOL_TIMEOUT_IMAGE_GEN,
    TOOL_TIMEOUT_WRITE,
)
from friday.logging_config import get_logger
from friday.safety import RiskLevel, classify_tool
from friday.tools._decorators import build_definitions, build_tool_map

_log = get_logger("tools")

_DOWNLOAD_INTENT_RE = re.compile(
    r"下载|安装包|安装程序|download|installer|setup\.exe|\.exe|\.msi",
    re.I,
)

# 下载/安装任务中不向模型暴露的工具（避免 PowerShell 弹窗与多次审批）
_DOWNLOAD_BLOCKED_TOOLS = frozenset({
    "run_powershell",
    "run_python",
    "run_python_script",
    "open_url",
})

_EAGER_MODULES = (
    "filesystem",
    "shell",
    "python_runner",
    "system",
    "extensions",
    "vision",
    "image_gen",
    "plan_tools",
    "memory_tools",
)
_LAZY_MODULES = ("documents", "media", "web")
_IMPORTED: set[str] = set()

_TOOL_MODULE: dict[str, str] = {
    "create_docx": "documents",
    "create_pptx": "documents",
    "read_pdf": "media",
    "read_excel": "media",
    "batch_rename": "media",
    "find_duplicates": "media",
    "zip_files": "media",
    "unzip_file": "media",
    "screenshot": "media",
    "clipboard_read": "media",
    "clipboard_write": "media",
    "browse_webpage": "web",
    "verify_download_source": "web",
    "download_file": "web",
    "download_software": "web",
    "describe_image": "vision",
    "vision_status": "vision",
    "generate_image": "image_gen",
    "image_gen_status": "image_gen",
}


def _import_tools_module(name: str) -> bool:
    if name in _IMPORTED:
        return True
    try:
        importlib.import_module(f"friday.tools.{name}")
        _IMPORTED.add(name)
        return True
    except Exception as exc:
        _log.warning(
            "工具模块加载失败 | module=friday.tools.%s | %s",
            name,
            exc,
            exc_info=True,
        )
        return False


def _rebuild_maps() -> None:
    global TOOL_MAP, TOOL_DEFINITIONS
    TOOL_MAP = build_tool_map()
    TOOL_DEFINITIONS = build_definitions()


for _module in _EAGER_MODULES:
    _import_tools_module(_module)
_rebuild_maps()

ToolFunc = Callable[..., str]

TOOL_DEFINITIONS: list[dict[str, Any]]
TOOL_MAP: dict[str, Callable[..., str]]

_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="friday-tool")

_TIMEOUT_BY_RISK = {
    RiskLevel.READ: TOOL_TIMEOUT_READ,
    RiskLevel.WRITE: TOOL_TIMEOUT_WRITE,
    RiskLevel.EXEC: TOOL_TIMEOUT_EXEC,
}


def ensure_all_tools() -> None:
    """加载全部工具模块（首次对话前调用）。"""
    for name in _LAZY_MODULES:
        _import_tools_module(name)
    _rebuild_maps()


def get_tool_definitions() -> list[dict[str, Any]]:
    ensure_all_tools()
    return TOOL_DEFINITIONS


def is_download_task_context(text: str) -> bool:
    return bool(_DOWNLOAD_INTENT_RE.search(text or ""))


def get_frozen_tool_definitions(settings: Any | None = None) -> list[dict[str, Any]]:
    """会话级冻结工具列表：仅按交互模式裁剪，不按单条用户消息动态隐藏（利于前缀缓存）。"""
    ensure_all_tools()
    defs = TOOL_DEFINITIONS
    if settings is not None:
        from friday.interaction_modes import normalize_mode, tool_allowed_in_mode

        mode = normalize_mode(getattr(settings, "interaction_mode", "agent"))
        if mode == "ask":
            defs = [
                d for d in defs
                if tool_allowed_in_mode((d.get("function") or {}).get("name", ""), mode)
            ]
            _log.info("Ask 模式 | 冻结只读工具 | tools=%d", len(defs))

    from friday.context import sort_tool_definitions
    from friday.tools.mcp_bridge import mcp_tool_definitions

    return sort_tool_definitions(defs + mcp_tool_definitions())


def get_all_tool_definitions(settings: Any | None = None) -> list[dict[str, Any]]:
    """内置工具 + MCP 工具（用于 API schema 展示）。"""
    return get_frozen_tool_definitions(settings)


def get_tool_definitions_for_messages(
    messages: list[dict[str, Any]],
    *,
    settings: Any | None = None,
) -> list[dict[str, Any]]:
    """根据最近用户消息与交互模式裁剪工具列表（非缓存路径，兼容旧调用）。"""
    ensure_all_tools()
    recent_user = ""
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            recent_user = str(msg.get("content", ""))
            break

    defs = get_frozen_tool_definitions(settings)
    if is_download_task_context(recent_user):
        defs = [
            d for d in defs
            if (d.get("function") or {}).get("name") not in _DOWNLOAD_BLOCKED_TOOLS
        ]
        _log.info("下载任务上下文 | 已隐藏 PowerShell/open_url | tools=%d", len(defs))
    return defs


def _ensure_tool_module(tool_name: str) -> None:
    module = _TOOL_MODULE.get(tool_name)
    if module:
        _import_tools_module(module)
        _rebuild_maps()


def _tool_timeout(name: str, arguments: dict[str, Any] | None = None) -> int:
    if name == "describe_image":
        return TOOL_TIMEOUT_VISION
    if name == "generate_image":
        from friday.image_gen import resolve_image_gen_timeouts
        from friday.storage import load_settings

        args = arguments or {}
        try:
            tool_timeout, _, _ = resolve_image_gen_timeouts(
                load_settings(),
                str(args.get("size", "")),
                prompt=str(args.get("prompt", "")),
            )
            return tool_timeout
        except Exception:
            return TOOL_TIMEOUT_IMAGE_GEN
    if name == "download_file":
        args = arguments or {}
        if args.get("_allow_large") or args.get("confirm_large_download"):
            return TOOL_TIMEOUT_DOWNLOAD_LARGE
        return TOOL_TIMEOUT_DOWNLOAD
    return _TIMEOUT_BY_RISK.get(classify_tool(name), TOOL_TIMEOUT_WRITE)


def _invoke_tool(name: str, arguments: dict[str, Any]) -> str:
    _ensure_tool_module(name)
    func = TOOL_MAP.get(name)
    if not func:
        return f"未知工具: {name}"
    return func(**arguments)


CANCELLED_TOOL_MESSAGE = "⏹ 操作已取消。"


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    cancel_event: threading.Event | None = None,
    on_heartbeat: Callable[[], None] | None = None,
    heartbeat_interval: float = 30.0,
) -> str:
    if name.startswith("mcp_"):
        from friday.tools.mcp_bridge import execute_mcp_tool

        result = execute_mcp_tool(name, arguments)
        if result is not None:
            return result

    _ensure_tool_module(name)
    if name not in TOOL_MAP:
        return f"未知工具: {name}"

    timeout = _tool_timeout(name, arguments)
    future = _TOOL_EXECUTOR.submit(_invoke_tool, name, arguments)
    deadline = time.monotonic() + timeout
    poll = max(0.05, min(CANCEL_POLL_INTERVAL, timeout))
    last_heartbeat = time.monotonic()
    heartbeat_every = max(5.0, float(heartbeat_interval))

    while True:
        if cancel_event and cancel_event.is_set():
            future.cancel()
            _log.info("工具执行已取消 | tool=%s", name)
            return CANCELLED_TOOL_MESSAGE

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _log.warning("工具执行超时 | tool=%s timeout=%ds", name, timeout)
            return f"工具执行超时（>{timeout}s），已终止。"

        if on_heartbeat and time.monotonic() - last_heartbeat >= heartbeat_every:
            on_heartbeat()
            last_heartbeat = time.monotonic()

        try:
            return future.result(timeout=min(poll, remaining))
        except FuturesTimeoutError:
            continue
        except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
            return f"工具执行失败: {exc}"


_TOOL_DISPLAY_NAMES: dict[str, str] = {
    "list_directory": "扫描目录",
    "search_files": "搜索文件",
    "read_text_file": "读取文件",
    "read_pdf": "读取 PDF",
    "read_excel": "读取 Excel",
    "write_text_file": "写入文件",
    "move_file": "移动文件",
    "organize_directory": "整理目录",
    "batch_rename": "批量重命名",
    "find_duplicates": "查找重复",
    "zip_files": "压缩文件",
    "unzip_file": "解压文件",
    "create_docx": "生成 Word",
    "create_pptx": "生成 PPT",
    "get_system_status": "查看系统",
    "get_disk_usage": "查看磁盘",
    "get_top_processes": "查看进程",
    "run_powershell": "执行 PowerShell",
    "run_python": "运行 Python",
    "run_python_script": "运行脚本",
    "python_env_info": "检查 Python 环境",
    "delete_file": "删除文件",
    "delete_directory": "删除目录",
    "copy_file": "复制文件",
    "get_file_info": "查看文件详情",
    "open_url": "打开网页",
    "open_app": "启动应用",
    "screenshot": "截屏",
    "clipboard_read": "读剪贴板",
    "clipboard_write": "写剪贴板",
    "get_network_info": "查看网络",
    "browse_webpage": "浏览网页",
    "verify_download_source": "验证下载源",
    "download_file": "下载文件",
    "download_software": "下载软件",
    "describe_image": "识别截图",
    "vision_status": "检查视觉",
    "generate_image": "生成图片",
    "image_gen_status": "检查生图",
    "update_session_plan": "更新计划",
    "remember_user_fact": "记住偏好",
}


def tool_display_name(name: str) -> str:
    key = (name or "").strip()
    return _TOOL_DISPLAY_NAMES.get(key, key or "操作")


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"__parse_error__": str(exc)}
