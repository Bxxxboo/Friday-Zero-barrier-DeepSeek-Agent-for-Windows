"""Agent 专用 Python 环境 — 位于工作区 .python-env，与星期五应用自身 venv 分离。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from friday.logging_config import get_logger
from friday.paths import bundle_dir, get_appdata_dir, is_frozen

_log = get_logger("python_env")

ENV_DIR_NAME = ".python-env"
REQUIREMENTS_NAME = "requirements-python.txt"
EMBED_PYTHON_VERSION = "3.12.10"
EMBED_PYTHON_DIR = get_appdata_dir() / "runtime" / f"python-{EMBED_PYTHON_VERSION}-embed-amd64"
_PACKAGES_OK_MARKER = ".packages_ok"
_packages_cache: dict[str, tuple[float, bool]] = {}
_PACKAGES_CACHE_TTL = 120.0


@dataclass
class PythonEnvStatus:
    ready: bool
    env_dir: str
    python_exe: str
    version: str
    message: str
    packages_installed: bool = False


def agent_env_dir(workspace: str) -> Path:
    return Path(workspace).expanduser().resolve() / ENV_DIR_NAME


def requirements_file() -> Path:
    return bundle_dir() / REQUIREMENTS_NAME


def _venv_python(env_dir: Path) -> Path:
    if sys.platform == "win32":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def embed_python_exe() -> Path | None:
    exe = EMBED_PYTHON_DIR / "python.exe"
    return exe if exe.is_file() else None


def _configure_embed_python(root: Path) -> None:
    for pth in root.glob("python*._pth"):
        lines = pth.read_text(encoding="utf-8").splitlines()
        updated: list[str] = []
        for line in lines:
            if line.strip() == "#import site":
                updated.append("import site")
            else:
                updated.append(line)
        pth.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _try_winget_python() -> Path | None:
    if sys.platform != "win32":
        return None
    winget = shutil.which("winget")
    if not winget:
        return None
    _log.info("尝试通过 winget 安装 Python 3.12（用户范围）…")
    try:
        proc = subprocess.run(
            [
                winget,
                "install",
                "-e",
                "--id",
                "Python.Python.3.12",
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
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-300:]
            _log.warning("winget 安装 Python 失败 | %s", tail)
            return None
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log.warning("winget 安装 Python 异常 | %s", exc)
        return None
    return find_system_python(skip_embed=True, skip_winget=True)


def _download_embed_python() -> Path | None:
    if embed_python_exe():
        return embed_python_exe()

    import urllib.error
    import urllib.request
    import zipfile

    url = (
        f"https://www.python.org/ftp/python/{EMBED_PYTHON_VERSION}/"
        f"python-{EMBED_PYTHON_VERSION}-embed-amd64.zip"
    )
    EMBED_PYTHON_DIR.parent.mkdir(parents=True, exist_ok=True)
    zip_path = EMBED_PYTHON_DIR.parent / f"python-{EMBED_PYTHON_VERSION}-embed-amd64.zip"
    _log.info("正在下载便携 Python %s …", EMBED_PYTHON_VERSION)
    try:
        with urllib.request.urlopen(url, timeout=180) as resp:
            zip_path.write_bytes(resp.read())
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(EMBED_PYTHON_DIR)
        zip_path.unlink(missing_ok=True)
    except (OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        _log.warning("下载/解压便携 Python 失败 | %s", exc)
        return None

    _configure_embed_python(EMBED_PYTHON_DIR)
    return embed_python_exe()


def find_system_python(*, skip_embed: bool = False, skip_winget: bool = False) -> Path | None:
    """查找可用于创建 venv 的系统 Python（3.11+）。"""
    candidates: list[Path | str] = []

    if not skip_embed:
        embed = embed_python_exe()
        if embed:
            candidates.append(embed)

    if not is_frozen():
        candidates.append(Path(sys.executable))

    local_app = os.getenv("LOCALAPPDATA", "")
    if local_app:
        for ver in ("Python312", "Python313", "Python311"):
            candidates.append(Path(local_app) / "Programs" / "Python" / ver / "python.exe")

    for name in ("python", "py"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    seen: set[str] = set()
    for raw in candidates:
        path = Path(raw)
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            out = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            text = (out.stdout or out.stderr or "").strip()
            if "Python 3." in text:
                minor = text.split("Python 3.", 1)[1].split(".", 1)[0]
                if minor.isdigit() and int(minor) >= 11:
                    return path
        except (OSError, subprocess.SubprocessError):
            continue

    if skip_winget:
        return None

    if is_frozen() and sys.platform == "win32" and not skip_embed:
        winget_py = _try_winget_python()
        if winget_py:
            return winget_py
        return _download_embed_python()

    return None


def _run_hidden(args: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    kwargs: dict = {
        "args": args,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "cwd": str(cwd) if cwd else None,
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(**kwargs)


def _python_version(python_exe: Path) -> str:
    try:
        cp = _run_hidden([str(python_exe), "--version"], timeout=15)
        return (cp.stdout or cp.stderr or "").strip() or "未知"
    except (OSError, subprocess.SubprocessError):
        return "未知"


def _packages_marker(env_dir: Path) -> Path:
    return env_dir / _PACKAGES_OK_MARKER


def _mark_packages_ok(env_dir: Path) -> None:
    try:
        _packages_marker(env_dir).write_text("1", encoding="utf-8")
        _packages_cache.pop(str(env_dir), None)
    except OSError:
        pass


def _packages_marker_valid(env_dir: Path, venv_py: Path) -> bool:
    marker = _packages_marker(env_dir)
    if not marker.is_file():
        return False
    try:
        return marker.stat().st_mtime >= venv_py.stat().st_mtime
    except OSError:
        return False


def _has_core_packages(python_exe: Path, env_dir: Path | None = None) -> bool:
    cache_key = str(python_exe)
    now = time.monotonic()
    cached = _packages_cache.get(cache_key)
    if cached and now - cached[0] < _PACKAGES_CACHE_TTL:
        return cached[1]

    if env_dir is not None and _packages_marker_valid(env_dir, python_exe):
        _packages_cache[cache_key] = (now, True)
        return True

    try:
        cp = _run_hidden(
            [str(python_exe), "-c", "import pandas, numpy, requests; print('ok')"],
            timeout=8,
        )
        ok = cp.returncode == 0 and "ok" in (cp.stdout or "")
    except (OSError, subprocess.SubprocessError):
        ok = False

    if ok and env_dir is not None:
        _mark_packages_ok(env_dir)
    _packages_cache[cache_key] = (now, ok)
    return ok


def _venv_is_stale(env_dir: Path) -> bool:
    """检测来自其他机器或已损坏的 venv。"""
    venv_py = _venv_python(env_dir)
    if not venv_py.is_file():
        return True

    cfg = env_dir / "pyvenv.cfg"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.lower().startswith("home"):
                continue
            home = Path(line.split("=", 1)[1].strip())
            if home and not home.is_dir():
                return True

    try:
        cp = _run_hidden([str(venv_py), "-c", "print('ok')"], timeout=8)
    except (OSError, subprocess.SubprocessError):
        return True
    return cp.returncode != 0 or "ok" not in (cp.stdout or "")


def resolve_agent_python(workspace: str, *, auto_setup: bool = False) -> tuple[Path | None, str]:
    """返回 Agent 应使用的 python.exe；auto_setup 时在缺失时尝试创建环境。"""
    ws = Path(workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    env_dir = agent_env_dir(str(ws))
    venv_py = _venv_python(env_dir)

    if venv_py.is_file():
        if _venv_is_stale(env_dir):
            _log.warning("工作区 Python 环境已失效，准备重建 | dir=%s", env_dir)
            shutil.rmtree(env_dir, ignore_errors=True)
            if not auto_setup:
                return None, (
                    "工作区 Python 环境已失效（常见于从其他电脑拷贝工作区）。"
                    "请在「设置 → Python 环境」点击「初始化 Python 环境」。"
                )
        else:
            return venv_py, str(env_dir)

    if not auto_setup:
        return None, f"工作区 Python 环境尚未初始化：{env_dir}"

    ok, msg = setup_agent_env(str(ws))
    if ok and venv_py.is_file():
        return venv_py, msg
    return None, msg


def setup_agent_env(workspace: str) -> tuple[bool, str]:
    """在工作区创建 .python-env 并安装 requirements-python.txt。"""
    ws = Path(workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    env_dir = agent_env_dir(str(ws))
    venv_py = _venv_python(env_dir)

    if venv_py.is_file():
        if _venv_is_stale(env_dir):
            _log.warning("重建失效的工作区 Python 环境 | dir=%s", env_dir)
            shutil.rmtree(env_dir, ignore_errors=True)
        elif _has_core_packages(venv_py, env_dir):
            return True, f"Python 环境已就绪：{venv_py} ({_python_version(venv_py)})"

    base = find_system_python()
    if not base:
        return False, (
            "无法自动准备 Python 3.11+（需联网）。"
            "可在设置 → Python 环境 重试，或手动安装：https://www.python.org/downloads/"
        )

    if env_dir.exists() and not venv_py.is_file():
        shutil.rmtree(env_dir, ignore_errors=True)

    _log.info("创建 Agent Python 环境 | workspace=%s", ws)
    try:
        cp = _run_hidden([str(base), "-m", "venv", str(env_dir)], cwd=ws, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "创建虚拟环境超时，请稍后重试。"
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        return False, f"创建虚拟环境失败：{err[:400]}"

    if not venv_py.is_file():
        return False, f"虚拟环境创建后未找到解释器：{venv_py}"

    req = requirements_file()
    if not req.is_file():
        return True, f"环境已创建（{_python_version(venv_py)}），但未找到 {REQUIREMENTS_NAME}，跳过依赖安装。"

    pip = env_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    pip_exe = str(pip) + (".exe" if sys.platform == "win32" else "")
    try:
        up = _run_hidden([pip_exe, "install", "--upgrade", "pip"], timeout=180)
        if up.returncode != 0:
            _log.warning("pip upgrade failed: %s", (up.stderr or up.stdout)[:200])
        cp = _run_hidden([pip_exe, "install", "-r", str(req)], timeout=900)
    except subprocess.TimeoutExpired:
        return False, "安装 Python 依赖超时，请稍后在设置页重试。"
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        return False, f"安装依赖失败：{err[:500]}"

    _mark_packages_ok(env_dir)
    return True, f"Python 环境已就绪：{venv_py} ({_python_version(venv_py)})"


def python_ready_light(workspace: str) -> bool:
    """轻量检查：不 spawn Python 进程。"""
    env_dir = agent_env_dir(workspace)
    venv_py = _venv_python(env_dir)
    return venv_py.is_file() and _packages_marker_valid(env_dir, venv_py)


def get_env_status(workspace: str) -> PythonEnvStatus:
    ws = Path(workspace).expanduser().resolve()
    env_dir = agent_env_dir(str(ws))
    venv_py = _venv_python(env_dir)

    if not venv_py.is_file():
        base = find_system_python()
        hint = (
            "点击「初始化 Python 环境」或在对话中让星期五执行复杂 Python 任务时会自动创建。"
        )
        if not base:
            hint = "未检测到 Python 3.11+。在设置页点「初始化 Python 环境」可自动下载便携 Python（需联网）。"
        return PythonEnvStatus(
            ready=False,
            env_dir=str(env_dir).replace("\\", "/"),
            python_exe="",
            version="",
            message=hint,
            packages_installed=False,
        )

    version = _python_version(venv_py)
    packages = _has_core_packages(venv_py, env_dir)
    return PythonEnvStatus(
        ready=packages,
        env_dir=str(env_dir).replace("\\", "/"),
        python_exe=str(venv_py).replace("\\", "/"),
        version=version,
        message="已就绪，可用于 run_python / run_python_script。" if packages else "环境存在但依赖未装全，请重新初始化。",
        packages_installed=packages,
    )


def env_dict(workspace: str) -> dict[str, object]:
    status = get_env_status(workspace)
    return {
        "ready": status.ready,
        "env_dir": status.env_dir,
        "python_exe": status.python_exe,
        "version": status.version,
        "message": status.message,
        "packages_installed": status.packages_installed,
        "system_python_available": find_system_python() is not None,
    }
