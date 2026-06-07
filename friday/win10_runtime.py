"""Windows 10/11 运行依赖检测与自动补齐（WebView2、VC++、.NET Framework）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir, is_frozen

_log = get_logger("win10_runtime")

WEBVIEW2_CLIENT_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
DOTNET472_RELEASE = 461808  # .NET Framework 4.7.2


@dataclass(frozen=True)
class RuntimeItem:
    id: str
    name: str
    ok: bool
    message: str
    can_auto_install: bool = False


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _read_reg_dword(root: int, path: str, name: str) -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(root, path) as key:
            value, kind = winreg.QueryValueEx(key, name)
            if kind in (winreg.REG_DWORD, winreg.REG_QWORD):
                return int(value)
    except OSError:
        return None
    return None


def _read_reg_str(root: int, path: str, name: str) -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value or "").strip()
    except OSError:
        return ""


def check_dotnet_framework() -> RuntimeItem:
    if sys.platform != "win32":
        return RuntimeItem("dotnet", ".NET Framework", True, "非 Windows 平台跳过")

    release = _read_reg_dword(
        0x80000002,  # HKEY_LOCAL_MACHINE
        r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full",
        "Release",
    )
    if release is not None and release >= DOTNET472_RELEASE:
        return RuntimeItem("dotnet", ".NET Framework", True, f"已安装（Release={release}）")

    try:
        import clr  # noqa: F401

        return RuntimeItem("dotnet", ".NET Framework", True, "pythonnet 可加载 CLR")
    except Exception:
        pass

    return RuntimeItem(
        "dotnet",
        ".NET Framework",
        False,
        "需要 .NET Framework 4.7.2 或更高：控制面板 → 启用或关闭 Windows 功能 → 勾选 .NET Framework 4.8",
        can_auto_install=False,
    )


def check_vc_redist() -> RuntimeItem:
    if sys.platform != "win32":
        return RuntimeItem("vcredist", "VC++ 运行库", True, "非 Windows 平台跳过")

    if _read_reg_dword(
        0x80000002,
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\AMD64",
        "Installed",
    ):
        return RuntimeItem("vcredist", "VC++ 运行库", True, "已安装（注册表）")

    try:
        import ctypes

        ctypes.WinDLL("vcruntime140.dll")
        return RuntimeItem("vcredist", "VC++ 运行库", True, "vcruntime140.dll 可用")
    except OSError:
        pass

    return RuntimeItem(
        "vcredist",
        "VC++ 运行库",
        False,
        "缺少 Visual C++ 2015–2022 运行库（可自动安装）",
        can_auto_install=True,
    )


def check_webview2() -> RuntimeItem:
    if sys.platform != "win32":
        return RuntimeItem("webview2", "WebView2 运行时", True, "非 Windows 平台跳过")

    for reg_root, reg_path in (
        (0x80000002, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
        (0x80000002, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
        (0x80000001, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_GUID}"),
    ):
        version = _read_reg_str(reg_root, reg_path, "pv")
        if version:
            return RuntimeItem("webview2", "WebView2 运行时", True, f"已安装（{version}）")

    pf = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    app_dir = Path(pf) / "Microsoft" / "EdgeWebView" / "Application"
    if app_dir.is_dir():
        for child in sorted(app_dir.iterdir(), reverse=True):
            if (child / "msedgewebview2.exe").is_file():
                return RuntimeItem("webview2", "WebView2 运行时", True, f"已安装（{child.name}）")

    user_pf = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "EdgeWebView"
    if user_pf.is_dir() and any(user_pf.rglob("msedgewebview2.exe")):
        return RuntimeItem("webview2", "WebView2 运行时", True, "已安装（用户目录）")

    return RuntimeItem(
        "webview2",
        "WebView2 运行时",
        False,
        "未检测到 WebView2（Win10 常见，可自动安装）",
        can_auto_install=True,
    )


def collect_runtime_status() -> list[RuntimeItem]:
    return [check_dotnet_framework(), check_vc_redist(), check_webview2()]


def runtime_status_payload() -> dict[str, object]:
    items = collect_runtime_status()
    return {
        "ready": all(item.ok for item in items if item.id != "vcredist" or item.ok),
        "all_ok": all(item.ok for item in items),
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "ok": item.ok,
                "message": item.message,
                "can_auto_install": item.can_auto_install,
            }
            for item in items
        ],
    }


def _bundled_installer(name: str) -> Path | None:
    if not is_frozen():
        return None
    exe_dir = Path(sys.executable).resolve().parent
    for base in (exe_dir, exe_dir.parent):
        candidate = base / "deps" / name
        if candidate.is_file():
            return candidate
    return None


def _download_file(url: str, dest: Path, *, timeout: int = 300) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return dest.is_file() and dest.stat().st_size > 0
    except (OSError, urllib.error.URLError) as exc:
        _log.warning("下载失败 | url=%s err=%s", url, exc)
        if dest.is_file():
            dest.unlink(missing_ok=True)
        return False


def _run_installer(exe: Path, args: list[str], *, timeout: int = 600) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [str(exe), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=_creationflags(),
        )
        if proc.returncode in (0, 1638, 3010):  # 已安装 / 需重启
            return True, "安装完成"
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        return False, tail or f"安装程序退出码 {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "安装超时"
    except OSError as exc:
        return False, str(exc)


def install_vc_redist(*, silent: bool = True) -> tuple[bool, str]:
    bundled = _bundled_installer("vc_redist.x64.exe")
    cache_dir = get_appdata_dir() / "runtime" / "installers"
    cache_dir.mkdir(parents=True, exist_ok=True)
    installer = bundled or cache_dir / "vc_redist.x64.exe"

    if not installer.is_file():
        _log.info("正在下载 VC++ 运行库…")
        if not _download_file(VC_REDIST_URL, installer):
            return False, "下载 VC++ 运行库失败，请检查网络"

    args = ["/install", "/quiet", "/norestart"] if silent else ["/install"]
    ok, detail = _run_installer(installer, args, timeout=600)
    if ok and check_vc_redist().ok:
        return True, "VC++ 运行库已安装"
    if check_vc_redist().ok:
        return True, "VC++ 运行库已就绪"
    return False, detail or "VC++ 运行库安装后仍未检测到"


def install_webview2(*, silent: bool = True) -> tuple[bool, str]:
    bundled = _bundled_installer("MicrosoftEdgeWebview2Setup.exe")
    cache_dir = get_appdata_dir() / "runtime" / "installers"
    cache_dir.mkdir(parents=True, exist_ok=True)
    installer = bundled or cache_dir / "MicrosoftEdgeWebview2Setup.exe"

    if not installer.is_file():
        _log.info("正在下载 WebView2 安装程序…")
        if not _download_file(WEBVIEW2_BOOTSTRAPPER_URL, installer, timeout=600):
            return False, "下载 WebView2 安装程序失败，请检查网络"

    args = ["/silent", "/install"] if silent else ["/install"]
    ok, detail = _run_installer(installer, args, timeout=900)
    if check_webview2().ok:
        return True, "WebView2 已安装"
    if ok:
        return False, "WebView2 安装程序已运行但未检测到运行时，请重启电脑后重试"
    return False, detail or "WebView2 安装失败"


def ensure_win10_runtime(*, auto_install: bool = True) -> tuple[bool, list[str]]:
    """检测并补齐 Win10 关键运行依赖。返回 (可启动 GUI, 消息列表)。"""
    if sys.platform != "win32":
        return True, []

    messages: list[str] = []
    dotnet = check_dotnet_framework()
    if not dotnet.ok:
        messages.append(dotnet.message)
        _log.error("缺少 .NET Framework | %s", dotnet.message)
        return False, messages

    vc = check_vc_redist()
    if not vc.ok:
        if auto_install and vc.can_auto_install:
            _log.info("正在自动安装 VC++ 运行库…")
            ok, msg = install_vc_redist()
            messages.append(f"VC++：{msg}")
            if not ok:
                _log.warning("VC++ 自动安装未确认成功 | %s", msg)
        else:
            messages.append(vc.message)

    wv2 = check_webview2()
    if not wv2.ok:
        if auto_install and wv2.can_auto_install:
            _log.info("正在自动安装 WebView2…")
            ok, msg = install_webview2()
            messages.append(f"WebView2：{msg}")
            if not check_webview2().ok:
                messages.append(
                    "WebView2 仍未就绪。可手动安装：https://developer.microsoft.com/microsoft-edge/webview2/"
                )
                return False, messages
        else:
            messages.append(wv2.message)
            return False, messages

    if not messages:
        messages.append("运行环境已就绪")
    return True, messages


def notify_runtime_failure(messages: list[str]) -> None:
    """无法启动时弹出系统对话框。"""
    if sys.platform != "win32":
        return
    body = "\n".join(messages) or "运行环境未满足要求。"
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            body + "\n\n详见 %APPDATA%\\Friday\\friday.log",
            "星期五 — 运行环境",
            0x00000010,  # MB_ICONERROR
        )
    except (AttributeError, OSError):
        pass
