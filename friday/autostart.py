"""Windows 登录自启：星期五桌面本体（静默，无 CMD 窗口）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import bundle_dir, get_appdata_dir, is_frozen

_log = get_logger("autostart")

TASK_NAME = "Friday Desktop"
STARTUP_VBS_NAME = "Friday-Desktop.vbs"
_META_FILE = "autostart.json"

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


def _startup_vbs_path() -> Path:
    return _startup_folder() / STARTUP_VBS_NAME


def resolve_launch_spec() -> tuple[str, str, str, str]:
    """返回 (executable, arguments, mode, error)。"""
    if sys.platform != "win32":
        return "", "", "", "仅 Windows 支持开机自启"

    if is_frozen():
        exe = Path(sys.executable).resolve()
        if not exe.is_file():
            return "", "", "", "未找到星期五可执行文件"
        return str(exe), "", "exe", ""

    root = bundle_dir()
    run_py = (root / "run.py").resolve()
    candidates = [
        root / ".venv" / "Scripts" / "pythonw.exe",
        root / ".python-env" / "Scripts" / "pythonw.exe",
    ]
    pythonw = next((p.resolve() for p in candidates if p.is_file()), None)
    if pythonw is None:
        import shutil

        found = shutil.which("pythonw")
        pythonw = Path(found).resolve() if found else None
    if pythonw and run_py.is_file():
        return str(pythonw), f'"{run_py}"', "dev", ""
    return "", "", "", "未找到 pythonw 或 run.py，无法配置自启"


def resolve_launch_command() -> tuple[str, str, str]:
    exe, args, mode, err = resolve_launch_spec()
    if err:
        return "", mode, err
    if args:
        return f'"{exe}" {args}', mode, ""
    return f'"{exe}"', mode, ""


def _task_command_line(exe: str, args: str) -> str:
    if args:
        return f'"{exe}" {args}'
    return f'"{exe}"'


def _write_hidden_vbs(path: Path, run_command: str) -> None:
    escaped = run_command.replace('"', '""')
    content = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run "{escaped}", 0, False\r\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-16")


def _read_vbs_run_command(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-16")
    except OSError:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return ""
    for line in text.splitlines():
        line = line.strip()
        if not line.lower().startswith('sh.run "'):
            continue
        inner = line[7:].strip()
        if inner.endswith(", 0, False"):
            inner = inner[: -len(", 0, False")]
        if inner.startswith('"') and inner.endswith('"'):
            inner = inner[1:-1]
        return inner.replace('""', '"')
    return ""


def _save_meta(*, launch: str, mode: str, method: str) -> None:
    payload = {"launch": launch, "mode": mode, "method": method}
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


def _install_startup_vbs(launch: str, mode: str) -> tuple[bool, str]:
    vbs_path = _startup_vbs_path()
    try:
        _write_hidden_vbs(vbs_path, launch)
        _save_meta(launch=launch, mode=mode, method="startup")
        return True, str(vbs_path)
    except OSError as exc:
        _log.exception("写入启动项 VBS 失败")
        return False, str(exc)


def _install_scheduled_task(exe: str, args: str, mode: str) -> tuple[bool, str]:
    task_run = _task_command_line(exe, args)
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
            "0000:15",
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
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err or "schtasks failed"
    _save_meta(launch=task_run, mode=mode, method="task")
    return True, TASK_NAME


def _remove_autostart_files() -> None:
    vbs_path = _startup_vbs_path()
    if vbs_path.is_file():
        try:
            vbs_path.unlink()
        except OSError:
            _log.exception("删除启动 VBS 失败")
    _delete_task(TASK_NAME)
    meta = _meta_path()
    if meta.is_file():
        try:
            meta.unlink()
        except OSError:
            pass


def autostart_status() -> dict[str, object]:
    exe, args, mode, err = resolve_launch_spec()
    launch = _task_command_line(exe, args) if exe else ""
    available = sys.platform == "win32" and not err
    vbs_path = _startup_vbs_path()
    task_on = _task_exists(TASK_NAME)
    enabled = vbs_path.is_file() or task_on
    method = "startup" if vbs_path.is_file() else ("task" if task_on else "")

    stale = False
    if enabled and launch:
        recorded = _load_meta().get("launch") or _read_vbs_run_command(vbs_path)
        if recorded and recorded != launch:
            stale = True

    detail = ""
    if err:
        detail = err
    elif not available:
        detail = "当前环境不支持配置开机自启"
    elif enabled and stale:
        detail = "自启仍指向旧路径，请关闭后重新开启以更新"
    elif enabled:
        detail = "登录 Windows 后约 15 秒内自动启动（无 CMD 窗口）"
    else:
        detail = "开启后写入当前用户的启动项；远程唤醒后需有人登录桌面"

    return {
        "available": available,
        "enabled": enabled,
        "ok": True,
        "method": method,
        "mode": mode,
        "launch": launch,
        "stale": stale,
        "detail": detail,
    }


def set_autostart_enabled(enabled: bool) -> dict[str, object]:
    if sys.platform != "win32":
        return {
            "ok": False,
            "enabled": False,
            "available": False,
            "message": "仅 Windows 支持开机自启",
            "detail": "仅 Windows 支持开机自启",
        }

    if not enabled:
        _remove_autostart_files()
        status = autostart_status()
        status["ok"] = True
        status["message"] = "已关闭开机自启"
        return status

    exe, args, mode, err = resolve_launch_spec()
    if err:
        return {
            "ok": False,
            "enabled": False,
            "available": False,
            "message": err,
            "detail": err,
        }

    launch = _task_command_line(exe, args)
    _remove_autostart_files()
    ok, info = _install_scheduled_task(exe, args, mode)
    method = "task"
    if not ok:
        _log.info("计划任务创建失败，回退启动文件夹 | %s", info)
        ok, info = _install_startup_vbs(launch, mode)
        method = "startup"
    if not ok:
        return {
            "ok": False,
            "enabled": False,
            "available": True,
            "message": f"配置失败：{info}",
            "detail": str(info),
        }

    status = autostart_status()
    status["ok"] = True
    status["method"] = method
    status["message"] = "已开启开机自启"
    return status
