"""星期五 结构化日志配置。

输出目标：
- %APPDATA%/Friday/friday.log  按天轮转，保留 7 天
- 控制台（CLI 模式，仅 WARNING 及以上；桌面 GUI 模式不写控制台）
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from friday.paths import get_appdata_dir


def setup_logging(*, verbose: bool = False) -> None:
    root = logging.getLogger("friday")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    # 避免重复添加 handler
    if root.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler —— 按天轮转，保留 7 天
    log_path = get_appdata_dir() / "friday.log"
    file_handler = TimedRotatingFileHandler(
        str(log_path), when="D", interval=1, backupCount=7, encoding="utf-8"
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

    root.debug("日志系统已初始化 | log_path=%s", log_path)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"friday.{name}")


def log_file_path() -> Path:
    return get_appdata_dir() / "friday.log"


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
