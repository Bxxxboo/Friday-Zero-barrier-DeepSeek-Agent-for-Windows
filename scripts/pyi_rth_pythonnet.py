"""PyInstaller 运行时：import clr / webview 之前配置 pythonnet 与 DLL 搜索路径。"""

from __future__ import annotations

import os
import sys


def _prepend_path(directory: str) -> None:
    if not directory or not os.path.isdir(directory):
        return
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(directory)
        except OSError:
            pass
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    if directory not in parts:
        os.environ["PATH"] = directory + os.pathsep + path


def _find_python_dll(directory: str) -> str:
    if not directory or not os.path.isdir(directory):
        return ""
    preferred = (
        "python312.dll",
        "python311.dll",
        "python310.dll",
        "python3.dll",
    )
    for name in preferred:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    for name in sorted(os.listdir(directory)):
        lower = name.lower()
        if lower.startswith("python") and lower.endswith(".dll"):
            return os.path.join(directory, name)
    return ""


def _unblock_tree(directory: str) -> None:
    """解除从浏览器下载后 Windows 附加的 Zone.Identifier，否则 DLL 无法加载。"""
    if sys.platform != "win32" or not directory or not os.path.isdir(directory):
        return
    try:
        import subprocess

        escaped = directory.replace("'", "''")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    f"Get-ChildItem -LiteralPath '{escaped}' -Recurse "
                    "-ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"
                ),
            ],
            timeout=180,
            creationflags=flags,
            capture_output=True,
        )
    except Exception:
        pass


if sys.platform == "win32" and getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))

    for folder in (exe_dir, base):
        _unblock_tree(folder)

    if base:
        os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
        arch = "amd64" if sys.maxsize > 2**32 else "x86"
        runtime_dir = os.path.join(base, "pythonnet", "runtime")
        for sub in (
            os.path.join(base, "clr_loader", "ffi", "dlls", arch),
            runtime_dir,
            base,
            exe_dir,
        ):
            _prepend_path(sub)

        py_dll = _find_python_dll(base) or _find_python_dll(exe_dir)
        if py_dll:
            os.environ.setdefault("PYTHONNET_PYDLL", py_dll)
