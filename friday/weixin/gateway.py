from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from friday.logging_config import get_logger
from friday.weixin.config import openclaw_state_dir
from friday.weixin.openclaw_cli import cli_available, run_openclaw

_log = get_logger("weixin.gateway")

DEFAULT_GATEWAY_PORT = 18789
_START_TIMEOUT_SEC = 20

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)


def _gateway_port() -> int:
    raw = os.environ.get("OPENCLAW_GATEWAY_PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_GATEWAY_PORT


def probe_gateway(*, port: int | None = None, timeout_sec: float = 2.0) -> bool:
    target_port = port if port is not None else _gateway_port()
    try:
        with socket.create_connection(("127.0.0.1", target_port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def gateway_status(*, port: int | None = None) -> dict[str, object]:
    target_port = port if port is not None else _gateway_port()
    return {
        "running": probe_gateway(port=target_port),
        "port": target_port,
        "cli_available": cli_available(),
    }


def _gateway_cmd_path() -> Path:
    return openclaw_state_dir() / "gateway.cmd"


def _parse_gateway_cmd(path: Path) -> tuple[list[str], dict[str, str]]:
    """从 gateway.cmd 解析 node 启动命令与环境变量。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    env: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r'^\s*set\s+"([^"]+)=([^"]*)"\s*$', line, re.I)
        if match:
            env[match.group(1)] = match.group(2)
            continue
        match = re.match(r"^\s*set\s+(\w+)=(.+?)\s*$", line, re.I)
        if match:
            env[match.group(1)] = match.group(2).strip()
    quoted = re.findall(r'"([^"]+\.exe)"\s+(\S+\.js)\s+gateway(?:\s+--port\s+(\d+))?', text, re.I)
    if quoted:
        node_exe, script, port = quoted[-1]
        args = [node_exe, script, "gateway"]
        if port:
            args.extend(["--port", port])
        return args, env
    return [], env


def _fallback_gateway_cmd(port: int) -> list[str] | None:
    node = shutil.which("node")
    if not node:
        return None
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "openclaw" / "dist" / "index.js",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "openclaw" / "dist" / "index.js",
    ]
    for script in candidates:
        if script.is_file():
            return [node, str(script), "gateway", "--port", str(port)]
    return None


def _spawn_hidden(args: list[str], *, extra_env: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    subprocess.Popen(
        args,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW | _DETACHED_PROCESS,
        close_fds=True,
    )


def _start_gateway_silent(*, port: int | None = None) -> tuple[bool, str]:
    """后台静默启动 Gateway，不弹出 CMD 窗口（不用 openclaw gateway restart）。"""
    target_port = port if port is not None else _gateway_port()
    cmd_path = _gateway_cmd_path()
    if cmd_path.is_file():
        try:
            args, env = _parse_gateway_cmd(cmd_path)
            if args:
                _spawn_hidden(args, extra_env=env)
                _log.info("已后台启动 OpenClaw Gateway（静默）| cmd=%s", " ".join(args[:3]))
                return True, "Gateway 已在后台启动"
            _spawn_hidden(["cmd", "/c", str(cmd_path)], extra_env=env)
            _log.info("已后台启动 OpenClaw Gateway（gateway.cmd）")
            return True, "Gateway 已在后台启动"
        except OSError as exc:
            return False, str(exc)

    fallback = _fallback_gateway_cmd(target_port)
    if fallback:
        try:
            _spawn_hidden(fallback, extra_env={"OPENCLAW_GATEWAY_PORT": str(target_port)})
            _log.info("已后台启动 OpenClaw Gateway（node 直启）")
            return True, "Gateway 已在后台启动"
        except OSError as exc:
            return False, str(exc)
    return False, "未找到 gateway.cmd 或 openclaw 安装路径"


def ensure_gateway_running(
    *,
    port: int | None = None,
    wait_sec: float = _START_TIMEOUT_SEC,
    force_restart: bool = False,
) -> dict[str, object]:
    """探测 Gateway；未运行时静默后台拉起（默认不 restart、不弹窗）。"""
    target_port = port if port is not None else _gateway_port()
    if probe_gateway(port=target_port) and not force_restart:
        return {"running": True, "started": False, "port": target_port}

    if force_restart and cli_available():
        try:
            run_openclaw(["gateway", "restart", "--force"], timeout=int(wait_sec))
        except (subprocess.TimeoutExpired, OSError) as exc:
            _log.warning("OpenClaw Gateway restart 失败 | %s", exc)

    if probe_gateway(port=target_port):
        return {"running": True, "started": force_restart, "port": target_port}

    ok, message = _start_gateway_silent(port=target_port)
    if not ok:
        return {
            "running": False,
            "started": False,
            "port": target_port,
            "error": message,
        }

    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if probe_gateway(port=target_port):
            _log.info("OpenClaw Gateway 已就绪 | port=%d", target_port)
            return {"running": True, "started": True, "port": target_port}
        time.sleep(0.5)

    _log.warning("OpenClaw Gateway 启动后仍不可连接 | port=%d", target_port)
    return {
        "running": False,
        "started": False,
        "port": target_port,
        "error": "Gateway 启动超时，可在设置 → 微信端 AI 重试",
    }


def ensure_gateway_running_background(*, wait_sec: float = _START_TIMEOUT_SEC) -> None:
    """后台静默检查/启动 Gateway，不阻塞调用方（用于定时保活）。"""
    import threading

    def _worker() -> None:
        if probe_gateway():
            return
        result = ensure_gateway_running(wait_sec=wait_sec)
        if result.get("running"):
            _log.info("后台 Gateway 就绪 | port=%s", result.get("port"))
        else:
            _log.warning("后台 Gateway 未就绪 | error=%s", result.get("error", ""))

    threading.Thread(target=_worker, daemon=True, name="weixin-gateway-ensure").start()


def ensure_gateway_running_async_delay(*, delay_sec: float = 4.0) -> None:
    """延迟在后台线程静默检查/启动 Gateway，不阻塞星期五启动。"""
    import threading

    from friday.storage import load_settings

    def _worker() -> None:
        time.sleep(max(0.5, delay_sec))
        if not getattr(load_settings(), "weixin_bridge_enabled", True):
            return
        if probe_gateway():
            return
        ensure_gateway_running_background()

    threading.Thread(target=_worker, daemon=True, name="weixin-gateway-deferred").start()
