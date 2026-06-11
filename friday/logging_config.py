"""星期五 结构化日志配置。

输出目标：
- %APPDATA%/Friday/friday.log  单文件大小上限 + 保留 N 天归档；启动时清理过期
- 控制台（CLI 模式，仅 WARNING 及以上；桌面 GUI 模式不写控制台）
"""

from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from friday.paths import get_appdata_dir

LOG_BASENAME = "friday.log"
LOG_MAX_BYTES = int(os.environ.get("FRIDAY_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_RETAIN_DAYS = int(os.environ.get("FRIDAY_LOG_RETAIN_DAYS", "7"))
LOG_BACKUP_COUNT = int(os.environ.get("FRIDAY_LOG_BACKUP_COUNT", "14"))


def log_file_path() -> Path:
    return get_appdata_dir() / LOG_BASENAME


def _rotated_log_paths() -> list[Path]:
    appdata = get_appdata_dir()
    return sorted(
        p
        for p in appdata.glob(f"{LOG_BASENAME}.*")
        if p.is_file() and p.name != LOG_BASENAME
    )


def purge_expired_logs(
    *,
    retain_days: int | None = None,
    now: float | None = None,
) -> list[str]:
    """删除超过保留期的轮转日志（启动时调用）。不删除当前 friday.log。"""
    days = LOG_RETAIN_DAYS if retain_days is None else max(1, retain_days)
    cutoff = (now if now is not None else time.time()) - days * 86400
    deleted: list[str] = []
    for path in _rotated_log_paths():
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted.append(str(path))
        except OSError:
            continue
    return deleted


def setup_logging(*, verbose: bool = False) -> None:
    root = logging.getLogger("friday")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    # 避免重复添加 handler
    if root.handlers:
        return

    purge_expired_logs()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = log_file_path()
    file_handler = RotatingFileHandler(
        str(log_path),
        maxBytes=max(1024, LOG_MAX_BYTES),
        backupCount=max(1, LOG_BACKUP_COUNT),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # 桌面 GUI 模式不写控制台，避免启动时弹出黑框
    gui_mode = bool(os.environ.get("FRIDAY_GUI")) or getattr(sys, "frozen", False)
    if not gui_mode:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG if verbose else logging.WARNING)
        console.setFormatter(fmt)
        root.addHandler(console)

    root.debug(
        "日志系统已初始化 | log_path=%s max_bytes=%d retain_days=%d",
        log_path,
        LOG_MAX_BYTES,
        LOG_RETAIN_DAYS,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"friday.{name}")


def read_recent_log_lines(max_lines: int = 30) -> list[str]:
    """读取日志文件尾部若干行，供设置页展示。"""
    path = log_file_path()
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    return lines[-max(1, min(max_lines, 100)) :]
