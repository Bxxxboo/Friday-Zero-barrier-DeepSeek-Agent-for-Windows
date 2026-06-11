"""星期五桌面版标识（AppData、端口、自启命名等）。"""

from __future__ import annotations

import os

_DEV_INSTANCE_PORT = 58766


def is_dev_edition() -> bool:
    """源码测试版（快捷方式带 --dev 或 FRIDAY_DEV=1）。"""
    return os.environ.get("FRIDAY_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


def window_title() -> str:
    if is_dev_edition():
        return "星期五（测试版）"
    return "星期五"


def display_version(version: str) -> str:
    if is_dev_edition():
        from friday.version import __dev_version__, __version__

        v = (version or __version__).strip()
        if v == __version__:
            return __dev_version__
        return f"{v}-dev"
    return version


def instance_port() -> int:
    if is_dev_edition():
        return _DEV_INSTANCE_PORT
    return 58765


def app_user_model_id() -> str:
    if is_dev_edition():
        return "Friday.AIDesktop.Dev.2"
    return "Friday.AIDesktop.2"


def appdata_folder_name() -> str:
    return "Friday"


def default_workspace_name() -> str:
    return "星期五"


def appdata_hint() -> str:
    return rf"%APPDATA%\{appdata_folder_name()}"


def autostart_task_name() -> str:
    return "Friday Desktop"


def autostart_vbs_name() -> str:
    return "Friday-Desktop.vbs"


def openclaw_autostart_task_name() -> str:
    return "Friday OpenClaw Gateway"


def openclaw_autostart_vbs_name() -> str:
    return "Friday-OpenClaw-Gateway.vbs"


def openclaw_launcher_vbs_name() -> str:
    return "Friday-OpenClaw-Gateway-Launcher.vbs"


def openclaw_gateway_port() -> int:
    return 18789
