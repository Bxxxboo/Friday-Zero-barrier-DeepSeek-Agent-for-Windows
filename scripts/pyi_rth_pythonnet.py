"""PyInstaller 运行时：在 import clr / webview 之前配置 pythonnet 与 DLL 搜索路径。"""

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
    if directory not in path.split(os.pathsep):
        os.environ["PATH"] = directory + os.pathsep + path


if sys.platform == "win32" and getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    if base:
        # pywebview(WinForms) 依赖 pythonnet；优先使用系统自带的 .NET Framework
        os.environ.setdefault("PYTHONNET_RUNTIME", "netfx")
        arch = "amd64" if sys.maxsize > 2**32 else "x86"
        for sub in (
            os.path.join(base, "clr_loader", "ffi", "dlls", arch),
            os.path.join(base, "pythonnet", "runtime"),
            base,
        ):
            _prepend_path(sub)
