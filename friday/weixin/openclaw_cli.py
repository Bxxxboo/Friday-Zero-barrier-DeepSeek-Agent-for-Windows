from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def resolve_openclaw_command() -> list[str]:
    """返回可执行的 openclaw 命令前缀（Windows 上可能是 cmd /c openclaw.cmd）。"""
    found = shutil.which("openclaw")
    if found:
        return [found]
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        cmd_path = Path(appdata) / "npm" / "openclaw.cmd"
        if cmd_path.is_file():
            return ["cmd", "/c", str(cmd_path)]
    return ["openclaw"]


def cli_available() -> bool:
    cli = resolve_openclaw_command()
    if cli != ["openclaw"]:
        return True
    return shutil.which("openclaw") is not None


def run_openclaw(
    args: list[str],
    *,
    timeout: int = 120,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    cmd = [*resolve_openclaw_command(), *args]
    return subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        timeout=timeout,
        creationflags=creationflags,
        env=os.environ.copy(),
    )
