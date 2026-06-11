"""未处理异常本地落盘 —— %APPDATA%/Friday/crashes/（M4.1）。"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir, is_frozen
from friday.version import __version__

_log = get_logger("crash")

_ORIGINAL_EXCEPTHOOK = sys.excepthook
_ORIGINAL_THREADING_EXCEPTHOOK = getattr(threading, "excepthook", None)
_INSTALLED = False

MAX_CRASH_FILES = 30


def crashes_dir() -> Path:
    path = get_appdata_dir() / "crashes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_crash_report(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
    *,
    context: str = "",
) -> str:
    from friday.runtime_info import runtime_info_payload

    info = runtime_info_payload()
    lines = [
        f"time_utc: {_utc_stamp()}",
        f"version: {__version__}",
        f"run_mode: {info.get('run_mode', '')}",
        f"main_process: {info.get('main_process_name', '')}",
        f"frozen: {is_frozen()}",
        f"python: {sys.version.split()[0]}",
        f"platform: {sys.platform}",
    ]
    if context:
        lines.append(f"context: {context}")
    lines.append("")
    lines.append("traceback:")
    lines.append("".join(traceback.format_exception(exc_type, exc_value, exc_tb)).rstrip())
    return "\n".join(lines) + "\n"


def _prune_old_reports() -> None:
    try:
        files = sorted(crashes_dir().glob("crash-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[MAX_CRASH_FILES:]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def write_crash_report(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
    *,
    context: str = "",
) -> Path | None:
    try:
        body = format_crash_report(exc_type, exc_value, exc_tb, context=context)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = crashes_dir() / f"crash-{stamp}-{os.getpid()}.log"
        path.write_text(body, encoding="utf-8")
        _prune_old_reports()
        _log.error("已写入崩溃报告 | path=%s", path)
        return path
    except Exception:
        _log.exception("写入崩溃报告失败")
        return None


def _maybe_record_startup_crash(context: str) -> None:
    try:
        from friday.update_rollback import record_startup_crash

        record_startup_crash(context=context)
    except Exception:
        pass


def _main_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    if exc_type is not KeyboardInterrupt:
        write_crash_report(exc_type, exc_value, exc_tb, context="main")
        _maybe_record_startup_crash("main")
    _ORIGINAL_EXCEPTHOOK(exc_type, exc_value, exc_tb)


def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    ctx = f"thread:{getattr(args.thread, 'name', 'unknown')}"
    write_crash_report(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        context=ctx,
    )
    _maybe_record_startup_crash(ctx)


def install_crash_handler() -> None:
    """注册全局未捕获异常钩子（幂等）。"""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    sys.excepthook = _main_excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook
