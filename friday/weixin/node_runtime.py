"""为微信桥接准备 Node.js / npm（系统已有则复用，否则自动安装到 AppData）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import get_appdata_dir

_log = get_logger("weixin.node")

NODE_VERSION = "22.14.0"
NODE_ZIP_NAME = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_ROOT = get_appdata_dir() / "runtime" / "node"
NODE_HOME = NODE_ROOT / f"node-v{NODE_VERSION}-win-x64"
NPM_GLOBAL = get_appdata_dir() / "runtime" / "npm-global"


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _system_npm() -> str | None:
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _friday_npm() -> str | None:
    candidate = NODE_HOME / "npm.cmd"
    return str(candidate) if candidate.is_file() else None


def npm_command() -> str | None:
    return _system_npm() or _friday_npm()


def npm_global_prefix() -> Path:
    NPM_GLOBAL.mkdir(parents=True, exist_ok=True)
    return NPM_GLOBAL


def openclaw_cmd_in_friday_prefix() -> Path | None:
    for name in ("openclaw.cmd", "openclaw"):
        path = NPM_GLOBAL / name
        if path.is_file():
            return path
    return None


def node_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if NODE_HOME.is_dir():
        node_bin = str(NODE_HOME)
        env["PATH"] = node_bin + os.pathsep + env.get("PATH", "")
    if extra:
        env.update(extra)
    return env


def _try_winget_node() -> bool:
    if os.name != "nt":
        return False
    winget = shutil.which("winget")
    if not winget:
        return False
    _log.info("尝试通过 winget 安装 Node.js LTS（用户范围）…")
    try:
        proc = subprocess.run(
            [
                winget,
                "install",
                "-e",
                "--id",
                "OpenJS.NodeJS.LTS",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--scope",
                "user",
            ],
            capture_output=True,
            text=True,
            timeout=900,
            encoding="utf-8",
            errors="replace",
            creationflags=_creationflags(),
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-300:]
            _log.warning("winget 安装 Node 失败 | code=%s %s", proc.returncode, tail)
            return False
        return _system_npm() is not None
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log.warning("winget 安装 Node 异常 | %s", exc)
        return False


def _download_portable_node() -> bool:
    if (NODE_HOME / "node.exe").is_file() and (NODE_HOME / "npm.cmd").is_file():
        return True

    NODE_ROOT.mkdir(parents=True, exist_ok=True)
    url = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ZIP_NAME}"
    zip_path = NODE_ROOT / NODE_ZIP_NAME
    _log.info("正在下载便携 Node.js %s …", NODE_VERSION)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            zip_path.write_bytes(resp.read())
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(NODE_ROOT)
        zip_path.unlink(missing_ok=True)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        _log.warning("下载/解压 Node 失败 | %s", exc)
        return False

    ok = (NODE_HOME / "node.exe").is_file() and (NODE_HOME / "npm.cmd").is_file()
    if ok:
        _log.info("便携 Node.js 已就绪 | path=%s", NODE_HOME)
    return ok


def ensure_node_npm() -> tuple[bool, str]:
    """确保本机可用 npm；必要时自动安装 Node（winget → 便携包）。"""
    existing = npm_command()
    if existing:
        return True, "Node.js 已可用"

    if _try_winget_node():
        npm = _system_npm()
        if npm:
            return True, "已通过 winget 安装 Node.js"

    if _download_portable_node():
        npm = _friday_npm()
        if npm:
            return True, f"已下载便携 Node.js {NODE_VERSION} 到 %APPDATA%\\Friday\\runtime\\node"

    return False, (
        "无法自动安装 Node.js（需联网）。请手动安装 Node 22+：https://nodejs.org，"
        "或在 PowerShell 执行：iwr -useb https://openclaw.ai/install.ps1 | iex"
    )


def run_npm_global(args: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    npm = npm_command()
    if not npm:
        raise FileNotFoundError("npm not available")
    prefix = npm_global_prefix()
    cmd = [npm, *args, "--prefix", str(prefix)]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        creationflags=_creationflags(),
        env=node_env(),
    )
