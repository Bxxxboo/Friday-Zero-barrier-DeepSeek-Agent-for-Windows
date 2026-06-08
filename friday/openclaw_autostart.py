"""OpenClaw Gateway 登录自启（静默，无 CMD 窗口）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir
from friday.weixin.config import openclaw_state_dir

_log = get_logger("openclaw_autostart")

TASK_NAME = "Friday OpenClaw Gateway"
STARTUP_VBS_NAME = "Friday-OpenClaw-Gateway.vbs"
_META_FILE = "openclaw_autostart.json"
_BOOT_DELAY = "0000:30"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _startup_folder() -> Path:
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def _meta_path() -> Path:
    return get_appdata_dir() / _META_FILE


def _launcher_vbs_path() -> Path:
    path = get_appdata_dir() / "runtime" / "Friday-OpenClaw-Gateway-Launcher.vbs"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _startup_vbs_path() -> Path:
    return _startup_folder() / STARTUP_VBS_NAME


def resolve_gateway_cmd() -> tuple[str, str]:
    """返回 (gateway.cmd 绝对路径, error)。"""
    if sys.platform != "win32":
        return "", "仅 Windows 支持 Gateway 自启"
    cmd_path = openclaw_state_dir() / "gateway.cmd"
    if not cmd_path.is_file():
        return "", f"未找到 gateway.cmd，请先在设置 → 微信端 AI 完成一键配置（{cmd_path}）"
    return str(cmd_path.resolve()), ""


def _write_hidden_vbs(path: Path, run_command: str) -> None:
    escaped = run_command.replace('"', '""')
    content = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run "{escaped}", 0, False\r\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-16")


def _gateway_run_command(gateway_cmd: str) -> str:
    return f'cmd /c ""{gateway_cmd}""'


def resolve_launch_spec() -> tuple[str, str, str, str]:
    """返回 (task_run, gateway_cmd, mode, error)。"""
    gateway_cmd, err = resolve_gateway_cmd()
    if err:
        return "", "", "", err
    launcher = _launcher_vbs_path()
    _write_hidden_vbs(launcher, _gateway_run_command(gateway_cmd))
    task_run = f'wscript.exe "{launcher}"'
    return task_run, gateway_cmd, "gateway.cmd", ""


def _save_meta(*, gateway_cmd: str, task_run: str, method: str) -> None:
    payload = {"gateway_cmd": gateway_cmd, "task_run": task_run, "method": method}
    _meta_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_meta() -> dict[str, str]:
    path = _meta_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _task_exists(name: str) -> bool:
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", name],
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    return proc.returncode == 0


def _delete_task(name: str) -> None:
    subprocess.run(
        ["schtasks", "/Delete", "/TN", name, "/F"],
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )


def _remove_autostart_files() -> None:
    for path in (_startup_vbs_path(),):
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                _log.exception("删除 Gateway 启动 VBS 失败")
    _delete_task(TASK_NAME)
    meta = _meta_path()
    if meta.is_file():
        try:
            meta.unlink()
        except OSError:
            pass


def openclaw_autostart_status() -> dict[str, object]:
    task_run, gateway_cmd, mode, err = resolve_launch_spec()
    available = sys.platform == "win32" and not err
    vbs_path = _startup_vbs_path()
    task_on = _task_exists(TASK_NAME)
    enabled = vbs_path.is_file() or task_on
    method = "startup" if vbs_path.is_file() else ("task" if task_on else "")

    stale = False
    if enabled and gateway_cmd:
        recorded = _load_meta().get("gateway_cmd", "")
        if recorded and recorded != gateway_cmd:
            stale = True

    detail = ""
    if err:
        detail = err
    elif not available:
        detail = "当前环境不支持 Gateway 自启"
    elif enabled and stale:
        detail = "自启仍指向旧 gateway.cmd，请关闭后重新开启"
    elif enabled:
        detail = "登录 Windows 后约 30 秒内自动启动 OpenClaw Gateway（无 CMD 窗口）"
    else:
        detail = "开启后 Gateway 随用户登录静默启动；需已完成微信桥接配置"

    return {
        "available": available,
        "enabled": enabled,
        "ok": True,
        "method": method,
        "mode": mode,
        "gateway_cmd": gateway_cmd,
        "stale": stale,
        "detail": detail,
    }


def set_openclaw_autostart_enabled(enabled: bool) -> dict[str, object]:
    if sys.platform != "win32":
        return {
            "ok": False,
            "enabled": False,
            "available": False,
            "message": "仅 Windows 支持 Gateway 自启",
            "detail": "仅 Windows 支持 Gateway 自启",
        }

    if not enabled:
        _remove_autostart_files()
        status = openclaw_autostart_status()
        status["ok"] = True
        status["message"] = "已关闭 Gateway 开机自启"
        return status

    task_run, gateway_cmd, _mode, err = resolve_launch_spec()
    if err:
        return {
            "ok": False,
            "enabled": False,
            "available": False,
            "message": err,
            "detail": err,
        }

    _remove_autostart_files()
    proc = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            TASK_NAME,
            "/TR",
            task_run,
            "/SC",
            "ONLOGON",
            "/DELAY",
            _BOOT_DELAY,
            "/RL",
            "LIMITED",
            "/F",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_CREATE_NO_WINDOW,
    )
    method = "task"
    if proc.returncode != 0:
        _log.info("Gateway 计划任务失败，回退启动文件夹 | %s", (proc.stderr or proc.stdout or "").strip())
        _write_hidden_vbs(_startup_vbs_path(), _gateway_run_command(gateway_cmd))
        method = "startup"
    _save_meta(gateway_cmd=gateway_cmd, task_run=task_run, method=method)

    status = openclaw_autostart_status()
    status["ok"] = True
    status["method"] = method
    status["message"] = "已开启 Gateway 开机自启"
    return status
